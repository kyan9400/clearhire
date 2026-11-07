// SPDX-License-Identifier: MIT
pragma solidity 0.8.37;

import {Script, console} from "forge-std/Script.sol";
import {AuditAnchor} from "../src/AuditAnchor.sol";

/// forge script script/Deploy.s.sol --rpc-url $RPC_URL --private-key $DEPLOYER_KEY --broadcast
/// PUBLISHER is the address the backend signs anchors with (`clearhire anchor-address` prints it).
contract Deploy is Script {
    function run() external returns (AuditAnchor deployed) {
        address publisher = vm.envAddress("PUBLISHER");
        vm.startBroadcast();
        deployed = new AuditAnchor(publisher);
        vm.stopBroadcast();
        console.log("AuditAnchor", address(deployed));
    }
}
