// SPDX-License-Identifier: MIT
pragma solidity 0.8.37;

/// @title AuditAnchor
/// @notice Public, append-only commitments to Clearhire's audit log: who (or which model) decided what
/// about a candidate. Once a period is anchored here, nobody (Clearhire included) can rewrite its history
/// without the change being provable.
///
/// For each finished period (an hour by default: the period number is hours since 1970-01-01 UTC) the
/// publisher records two values:
/// - `head`: the SHA-256 hash of the last log entry anchored. Every entry's hash covers the previous one,
///   so the head commits to the whole history up to that moment;
/// - `root`: the Merkle root of the entries anchored, so a single decision can be proven against the chain
///   (`verifyEntry`) without revealing any other entry.
///
/// Leaves are `keccak256(bytes.concat(keccak256(abi.encodePacked(id, entryHash))))` (hashed twice, so a
/// leaf can never be confused with an inner node), and pairs are hashed in sorted order: the scheme of
/// OpenZeppelin's MerkleProof, which keeps proofs free of left/right flags.
contract AuditAnchor {
    struct Anchor {
        bytes32 root;
        bytes32 head;
        uint64 firstId;
        uint64 lastId;
        uint64 entries;
        uint64 anchoredAt;
    }

    address public owner;
    address public pendingOwner;
    mapping(address => bool) public isPublisher;

    /// @notice The most recent anchored period; 0 before the first anchor.
    uint32 public latestPeriod;
    /// @notice The last audit entry id anchored so far: the next anchor must start after it.
    uint64 public latestId;
    uint32 public anchorCount;
    mapping(uint32 period => Anchor) private _anchors;

    event Anchored(uint32 indexed period, bytes32 root, bytes32 head, uint64 firstId, uint64 lastId, uint64 entries);
    event PublisherSet(address indexed publisher, bool allowed);
    event OwnershipTransferStarted(address indexed from, address indexed to);
    event OwnershipTransferred(address indexed from, address indexed to);

    error NotOwner();
    error NotPublisher();
    error NotPendingOwner();
    error ZeroAddress();
    error EmptyAnchor();
    error BadRange(uint64 firstId, uint64 lastId, uint64 entries);
    error PeriodNotAfterLatest(uint32 period, uint32 latestPeriod);
    error EntriesOverlap(uint64 firstId, uint64 latestId);

    modifier onlyOwner() {
        if (msg.sender != owner) revert NotOwner();
        _;
    }

    constructor(address publisher) {
        if (publisher == address(0)) revert ZeroAddress();
        owner = msg.sender;
        emit OwnershipTransferred(address(0), msg.sender);
        isPublisher[publisher] = true;
        emit PublisherSet(publisher, true);
    }

    // ---------------------------------------------------------------- anchoring

    /// @notice Record a finished period. Periods only move forward and entry ranges never overlap, so an
    /// anchored period cannot be replaced, and history cannot be re-anchored differently.
    function anchor(uint32 period, bytes32 root, bytes32 head, uint64 firstId, uint64 lastId, uint64 entries) external {
        if (!isPublisher[msg.sender]) revert NotPublisher();
        if (root == bytes32(0) || head == bytes32(0) || entries == 0) revert EmptyAnchor();
        // ids come from a database sequence: increasing, but a rolled-back transaction can skip one
        if (firstId == 0 || lastId < firstId || entries > lastId - firstId + 1) {
            revert BadRange(firstId, lastId, entries);
        }
        if (anchorCount != 0 && period <= latestPeriod) revert PeriodNotAfterLatest(period, latestPeriod);
        if (firstId <= latestId) revert EntriesOverlap(firstId, latestId);

        // casting to 'uint64' is safe because a Unix timestamp needs 64 bits only in 584 billion years
        // forge-lint: disable-next-line(unsafe-typecast)
        _anchors[period] = Anchor(root, head, firstId, lastId, entries, uint64(block.timestamp));
        latestPeriod = period;
        latestId = lastId;
        anchorCount += 1;
        emit Anchored(period, root, head, firstId, lastId, entries);
    }

    /// @notice What was recorded for a period; `entries == 0` when the period was never anchored.
    function anchorOf(uint32 period) external view returns (Anchor memory) {
        return _anchors[period];
    }

    // ---------------------------------------------------------------- verification

    /// @notice Whether one log entry (its id and SHA-256 hash) is in an anchored period.
    function verifyEntry(uint32 period, uint64 id, bytes32 entryHash, bytes32[] calldata proof)
        external
        view
        returns (bool)
    {
        Anchor storage a = _anchors[period];
        if (a.entries == 0 || id < a.firstId || id > a.lastId) return false;
        return processProof(proof, leaf(id, entryHash)) == a.root;
    }

    function leaf(uint64 id, bytes32 entryHash) public pure returns (bytes32) {
        return keccak256(bytes.concat(keccak256(abi.encodePacked(id, entryHash))));
    }

    function processProof(bytes32[] calldata proof, bytes32 node) public pure returns (bytes32) {
        for (uint256 i = 0; i < proof.length; i++) {
            node = _hashPair(node, proof[i]);
        }
        return node;
    }

    function _hashPair(bytes32 a, bytes32 b) private pure returns (bytes32) {
        return a < b ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }

    // ---------------------------------------------------------------- administration

    function setPublisher(address publisher, bool allowed) external onlyOwner {
        if (publisher == address(0)) revert ZeroAddress();
        // the change is announced by PublisherSet on the next line
        // forge-lint: disable-next-line(missing-events-access-control)
        isPublisher[publisher] = allowed;
        emit PublisherSet(publisher, allowed);
    }

    /// @notice Two steps, so ownership is never handed to an address nobody controls. The zero address
    /// cancels a pending transfer.
    // forge-lint: disable-next-line(missing-zero-check)
    function transferOwnership(address to) external onlyOwner {
        pendingOwner = to;
        emit OwnershipTransferStarted(owner, to);
    }

    function acceptOwnership() external {
        if (msg.sender != pendingOwner) revert NotPendingOwner();
        emit OwnershipTransferred(owner, msg.sender);
        owner = msg.sender;
        pendingOwner = address(0);
    }
}
