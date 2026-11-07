"""Talking to the AuditAnchor contract over plain JSON-RPC: any EVM chain (Anvil, Base Sepolia, Ethereum).

Transactions are signed locally with eth-account and calls are ABI-encoded with eth-abi; no web3.py.
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from functools import cache
from importlib import resources
from typing import Any

import httpx
from eth_abi.abi import decode, encode
from eth_account import Account
from eth_utils.address import to_checksum_address

from clearhire.anchoring.merkle import keccak256

ANCHOR_SIGNATURE = "anchor(uint32,bytes32,bytes32,uint64,uint64,uint64)"
ANCHOR_OF_SIGNATURE = "anchorOf(uint32)"
VERIFY_SIGNATURE = "verifyEntry(uint32,uint64,bytes32,bytes32[])"
ANCHOR_TUPLE = "(bytes32,bytes32,uint64,uint64,uint64,uint64)"


class ChainError(RuntimeError):
    pass


@cache
def artifact() -> dict[str, Any]:
    """The compiled contract (contracts/out, copied here by `make contract-artifact`; CI checks it is current)."""
    data: dict[str, Any] = json.loads(
        resources.files("clearhire.anchoring").joinpath("AuditAnchor.json").read_text()
    )
    return data


def selector(signature: str) -> bytes:
    return keccak256(signature.encode())[:4]


@dataclass(frozen=True)
class OnChainAnchor:
    root: bytes
    head: bytes
    first_id: int
    last_id: int
    entries: int
    anchored_at: int


@dataclass(frozen=True)
class Receipt:
    tx_hash: str
    block: int


class Chain:
    def __init__(self, rpc_url: str, private_key: str | None = None, contract: str | None = None, *,
                 transport: httpx.AsyncBaseTransport | None = None, poll: float = 1.0, timeout: float = 120) -> None:  # fmt: skip
        self.account = Account.from_key(private_key) if private_key else None
        self.contract: str | None = str(to_checksum_address(contract)) if contract else None  # eth-account wants checksums
        self.poll, self.timeout = poll, timeout
        self._client = httpx.AsyncClient(timeout=30, transport=transport)
        self._url = rpc_url
        self._ids = 0

    @property
    def address(self) -> str | None:
        return self.account.address if self.account else None

    async def rpc(self, method: str, *params: Any) -> Any:
        self._ids += 1
        try:
            response = await self._client.post(
                self._url, json={"jsonrpc": "2.0", "id": self._ids, "method": method, "params": list(params)}
            )
            response.raise_for_status()
            body = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ChainError(f"{method}: the chain node is unavailable ({type(exc).__name__})") from exc
        if "error" in body:
            raise ChainError(f"{method}: {body['error'].get('message', body['error'])}")
        return body["result"]

    async def chain_id(self) -> int:
        return int(await self.rpc("eth_chainId"), 16)

    # ------------------------------------------------------------ writes

    async def _send(self, data: bytes, to: str | None) -> dict[str, Any]:
        """Sign an EIP-1559 transaction, send it, and wait for its receipt. `to=None` creates a contract."""
        if self.account is None:
            raise ChainError("no signing key configured")
        sender = self.account.address
        estimate: dict[str, Any] = {"from": sender, "data": "0x" + data.hex()}
        tx: dict[str, Any] = {"type": 2, "data": data, "value": 0}
        if to:
            estimate["to"] = tx["to"] = to_checksum_address(to)
        gas = int(await self.rpc("eth_estimateGas", estimate), 16)
        base = int((await self.rpc("eth_getBlockByNumber", "latest", False))["baseFeePerGas"], 16)
        tip = int(await self.rpc("eth_maxPriorityFeePerGas"), 16)
        nonce = int(await self.rpc("eth_getTransactionCount", sender, "pending"), 16)
        tx |= {"chainId": await self.chain_id(), "nonce": nonce, "gas": gas * 12 // 10,
               "maxPriorityFeePerGas": tip, "maxFeePerGas": base * 2 + tip}  # fmt: skip
        signed = self.account.sign_transaction(tx)
        tx_hash = await self.rpc("eth_sendRawTransaction", "0x" + signed.raw_transaction.hex())
        return await self._wait(tx_hash)

    async def _wait(self, tx_hash: str) -> dict[str, Any]:
        waited = 0.0
        while waited < self.timeout:
            receipt: dict[str, Any] | None = await self.rpc("eth_getTransactionReceipt", tx_hash)
            if receipt:
                if int(receipt["status"], 16) != 1:
                    raise ChainError(f"transaction {tx_hash} reverted")
                return receipt
            await asyncio.sleep(self.poll)
            waited += self.poll
        raise ChainError(f"transaction {tx_hash} was not mined within {self.timeout:.0f} s")

    @staticmethod
    def _receipt(raw: dict[str, Any]) -> Receipt:
        return Receipt(raw["transactionHash"], int(raw["blockNumber"], 16))

    async def deploy(self, publisher: str) -> tuple[str, Receipt]:
        bytecode = bytes.fromhex(artifact()["bytecode"].removeprefix("0x"))
        raw = await self._send(bytecode + encode(["address"], [publisher]), None)
        self.contract = str(to_checksum_address(raw["contractAddress"]))
        return self.contract, self._receipt(raw)

    async def anchor(
        self, period: int, root: bytes, head: bytes, first_id: int, last_id: int, entries: int
    ) -> Receipt:
        args = encode(
            ["uint32", "bytes32", "bytes32", "uint64", "uint64", "uint64"],
            [period, root, head, first_id, last_id, entries],
        )
        return self._receipt(await self._send(selector(ANCHOR_SIGNATURE) + args, self._contract()))

    # ------------------------------------------------------------ reads

    async def _call(self, data: bytes) -> bytes:
        result = await self.rpc("eth_call", {"to": self._contract(), "data": "0x" + data.hex()}, "latest")
        return bytes.fromhex(result.removeprefix("0x"))

    async def anchor_of(self, period: int) -> OnChainAnchor | None:
        raw = await self._call(selector(ANCHOR_OF_SIGNATURE) + encode(["uint32"], [period]))
        root, head, first_id, last_id, entries, at = decode([ANCHOR_TUPLE], raw)[0]
        return OnChainAnchor(root, head, first_id, last_id, entries, at) if entries else None

    async def verify_entry(self, period: int, entry_id: int, entry_hash: bytes, proof: list[bytes]) -> bool:
        args = encode(["uint32", "uint64", "bytes32", "bytes32[]"], [period, entry_id, entry_hash, proof])
        (ok,) = decode(["bool"], await self._call(selector(VERIFY_SIGNATURE) + args))
        return bool(ok)

    def _contract(self) -> str:
        if not self.contract:
            raise ChainError("no AuditAnchor contract address configured")
        return self.contract

    async def close(self) -> None:
        await self._client.aclose()
