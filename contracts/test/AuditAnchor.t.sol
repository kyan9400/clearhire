// SPDX-License-Identifier: MIT
pragma solidity 0.8.37;

import {Test} from "forge-std/Test.sol";
import {AuditAnchor} from "../src/AuditAnchor.sol";

contract AuditAnchorTest is Test {
    AuditAnchor internal anchors;
    address internal publisher = makeAddr("publisher");
    address internal stranger = makeAddr("stranger");

    bytes32 internal constant ROOT = keccak256("root");
    bytes32 internal constant HEAD = keccak256("head");

    function setUp() public {
        anchors = new AuditAnchor(publisher);
    }

    // ------------------------------------------------------------ anchoring rules

    function test_publisherAnchorsAPeriod() public {
        vm.expectEmit(address(anchors));
        emit AuditAnchor.Anchored(20_400, ROOT, HEAD, 1, 10, 10);
        vm.prank(publisher);
        anchors.anchor(20_400, ROOT, HEAD, 1, 10, 10);

        AuditAnchor.Anchor memory a = anchors.anchorOf(20_400);
        assertEq(a.root, ROOT);
        assertEq(a.head, HEAD);
        assertEq(a.entries, 10);
        assertEq(a.anchoredAt, block.timestamp);
        assertEq(anchors.latestPeriod(), 20_400);
        assertEq(anchors.latestId(), 10);
        assertEq(anchors.anchorCount(), 1);
    }

    function test_onlyPublishersAnchor() public {
        vm.prank(stranger);
        vm.expectRevert(AuditAnchor.NotPublisher.selector);
        anchors.anchor(20_400, ROOT, HEAD, 1, 10, 10);
    }

    function test_aPeriodCannotBeReplacedOrBackdated() public {
        vm.startPrank(publisher);
        anchors.anchor(20_400, ROOT, HEAD, 1, 10, 10);
        vm.expectRevert(abi.encodeWithSelector(AuditAnchor.PeriodNotAfterLatest.selector, 20_400, 20_400));
        anchors.anchor(20_400, keccak256("other"), HEAD, 11, 20, 10);
        vm.expectRevert(abi.encodeWithSelector(AuditAnchor.PeriodNotAfterLatest.selector, 20_399, 20_400));
        anchors.anchor(20_399, ROOT, HEAD, 11, 20, 10);
        vm.stopPrank();
    }

    function test_entryRangesNeverOverlap() public {
        vm.startPrank(publisher);
        anchors.anchor(20_400, ROOT, HEAD, 1, 10, 10);
        vm.expectRevert(abi.encodeWithSelector(AuditAnchor.EntriesOverlap.selector, 10, 10));
        anchors.anchor(20_401, ROOT, HEAD, 10, 20, 11);
        anchors.anchor(20_405, ROOT, HEAD, 14, 20, 6); // later periods and skipped ids are fine
        vm.stopPrank();
    }

    function test_rejectsEmptyOrInconsistentAnchors() public {
        vm.startPrank(publisher);
        vm.expectRevert(AuditAnchor.EmptyAnchor.selector);
        anchors.anchor(20_400, bytes32(0), HEAD, 1, 10, 10);
        vm.expectRevert(AuditAnchor.EmptyAnchor.selector);
        anchors.anchor(20_400, ROOT, HEAD, 1, 10, 0);
        vm.expectRevert(abi.encodeWithSelector(AuditAnchor.BadRange.selector, 5, 4, 1));
        anchors.anchor(20_400, ROOT, HEAD, 5, 4, 1);
        vm.expectRevert(abi.encodeWithSelector(AuditAnchor.BadRange.selector, 1, 10, 11));
        anchors.anchor(20_400, ROOT, HEAD, 1, 10, 11);
        vm.stopPrank();
    }

    // ------------------------------------------------------------ administration

    function test_ownerManagesPublishers() public {
        anchors.setPublisher(stranger, true);
        vm.prank(stranger);
        anchors.anchor(20_400, ROOT, HEAD, 1, 1, 1);
        anchors.setPublisher(publisher, false);
        vm.prank(publisher);
        vm.expectRevert(AuditAnchor.NotPublisher.selector);
        anchors.anchor(20_401, ROOT, HEAD, 2, 2, 1);
        vm.prank(stranger);
        vm.expectRevert(AuditAnchor.NotOwner.selector);
        anchors.setPublisher(stranger, false);
    }

    function test_ownershipMovesInTwoSteps() public {
        anchors.transferOwnership(stranger);
        assertEq(anchors.owner(), address(this));
        vm.prank(publisher);
        vm.expectRevert(AuditAnchor.NotPendingOwner.selector);
        anchors.acceptOwnership();
        vm.prank(stranger);
        anchors.acceptOwnership();
        assertEq(anchors.owner(), stranger);
        assertEq(anchors.pendingOwner(), address(0));
    }

    // ------------------------------------------------------------ proofs

    /// Any entry of any anchor of up to 64 entries is proven by its Merkle path, and only its own entry is.
    function testFuzz_everyEntryProvesAndNothingElseDoes(uint8 size, uint256 seed, uint8 pick) public {
        uint256 n = bound(size, 1, 64);
        uint64 firstId = 1000;
        bytes32[] memory hashes = new bytes32[](n);
        bytes32[] memory leaves = new bytes32[](n);
        for (uint256 i = 0; i < n; i++) {
            hashes[i] = keccak256(abi.encode(seed, i));
            leaves[i] = anchors.leaf(firstId + uint64(i), hashes[i]);
        }
        bytes32 root = _root(leaves);
        vm.prank(publisher);
        anchors.anchor(20_400, root, hashes[n - 1], firstId, firstId + uint64(n) - 1, uint64(n));

        uint256 k = bound(pick, 0, n - 1);
        bytes32[] memory proof = _proof(leaves, k);
        assertTrue(anchors.verifyEntry(20_400, firstId + uint64(k), hashes[k], proof));
        // a changed decision, a moved entry, or another period: all rejected
        assertFalse(anchors.verifyEntry(20_400, firstId + uint64(k), keccak256("rewritten"), proof));
        if (n > 1) assertFalse(anchors.verifyEntry(20_400, firstId + uint64((k + 1) % n), hashes[k], proof));
        assertFalse(anchors.verifyEntry(20_401, firstId + uint64(k), hashes[k], proof));
    }

    /// The backend builds trees in Python; this replays the proofs it wrote (clearhire anchor-fixture).
    function test_proofsFromTheBackendVerify() public {
        string memory json = vm.readFile("test/fixtures/merkle.json");
        bytes32 root = vm.parseJsonBytes32(json, ".root");
        uint64 firstId = uint64(vm.parseJsonUint(json, ".first_id"));
        uint64 lastId = uint64(vm.parseJsonUint(json, ".last_id"));
        uint256 count = vm.parseJsonUint(json, ".count");
        vm.prank(publisher);
        anchors.anchor(20_400, root, vm.parseJsonBytes32(json, ".head"), firstId, lastId, uint64(count));
        for (uint256 i = 0; i < count; i++) {
            string memory at = string.concat(".entries[", vm.toString(i), "]");
            uint64 id = uint64(vm.parseJsonUint(json, string.concat(at, ".id")));
            bytes32 hash = vm.parseJsonBytes32(json, string.concat(at, ".hash"));
            bytes32[] memory proof = vm.parseJsonBytes32Array(json, string.concat(at, ".proof"));
            assertEq(anchors.leaf(id, hash), vm.parseJsonBytes32(json, string.concat(at, ".leaf")));
            assertTrue(anchors.verifyEntry(20_400, id, hash, proof));
        }
    }

    // ------------------------------------------------------------ a reference tree, as the backend builds it

    /// Levels are built pairwise from the left; an odd node at the end of a level is carried up as it is.
    function _root(bytes32[] memory level) internal pure returns (bytes32) {
        while (level.length > 1) level = _up(level);
        return level[0];
    }

    function _proof(bytes32[] memory level, uint256 index) internal pure returns (bytes32[] memory) {
        bytes32[] memory path = new bytes32[](8);
        uint256 used = 0;
        while (level.length > 1) {
            uint256 sibling = index ^ 1;
            if (sibling < level.length) path[used++] = level[sibling];
            level = _up(level);
            index /= 2;
        }
        bytes32[] memory out = new bytes32[](used);
        for (uint256 i = 0; i < used; i++) {
            out[i] = path[i];
        }
        return out;
    }

    function _up(bytes32[] memory level) internal pure returns (bytes32[] memory next) {
        next = new bytes32[]((level.length + 1) / 2);
        for (uint256 i = 0; i < level.length; i += 2) {
            if (i + 1 == level.length) {
                next[i / 2] = level[i];
            } else {
                (bytes32 a, bytes32 b) = level[i] < level[i + 1] ? (level[i], level[i + 1]) : (level[i + 1], level[i]);
                next[i / 2] = keccak256(abi.encodePacked(a, b));
            }
        }
    }
}
