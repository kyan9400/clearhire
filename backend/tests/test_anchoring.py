"""Anchoring the audit log: the Merkle maths, the JSON-RPC client, and the whole flow on a real chain.

The flow tests need PostgreSQL (CLEARHIRE_TEST_DATABASE_URL); the chain tests also need an Anvil node
(ANVIL_URL, e.g. `docker run -p 8545:8545 ghcr.io/foundry-rs/foundry:v1.8.6 "anvil --host 0.0.0.0"`).
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from eth_abi.abi import encode
from sqlalchemy import select, update

from clearhire import audit
from clearhire.anchoring import merkle
from clearhire.anchoring.chain import Chain, ChainError, OnChainAnchor, Receipt, selector
from clearhire.anchoring.fixture import fixture
from clearhire.anchoring.service import anchor_pending, check_all, period_of, prove
from clearhire.db import session as db_session
from clearhire.db.models import AuditEntry
from test_api import api, database_url, login  # noqa: F401 - the API fixture and what it needs

# Anvil's first development account: a publicly known key, only ever used on a local test chain
ANVIL_KEY = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
HOUR = 3600


def h(i: int) -> bytes:
    return hashlib.sha256(str(i).encode()).digest()


# ---------------------------------------------------------------- Merkle trees


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 7, 8, 13, 16, 33])
def test_every_entry_proves_and_a_changed_one_does_not(size: int) -> None:
    ids = [100 + 3 * i for i in range(size)]
    tree = merkle.build([merkle.leaf(i, h(i)) for i in ids])
    for index, entry_id in enumerate(ids):
        proof = tree.proof(index)
        assert merkle.verify(tree.root, entry_id, h(entry_id), proof)
        assert not merkle.verify(tree.root, entry_id, h(entry_id + 1), proof)
        assert not merkle.verify(tree.root, entry_id + 1, h(entry_id), proof)


def test_leaves_are_hashed_twice_and_inputs_checked() -> None:
    once = merkle.keccak256((7).to_bytes(8, "big") + h(7))
    assert merkle.leaf(7, h(7)) == merkle.keccak256(once)
    with pytest.raises(ValueError):
        merkle.leaf(0, h(1))
    with pytest.raises(ValueError):
        merkle.leaf(1, b"short")
    assert merkle.keccak256(b"").hex() == "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470"


def test_the_contract_fixture_is_current() -> None:
    committed = json.loads((Path(__file__).parents[2] / "contracts/test/fixtures/merkle.json").read_text())
    assert committed == fixture()  # regenerate with: clearhire anchor-fixture


# ---------------------------------------------------------------- the JSON-RPC client


async def test_reads_are_encoded_and_decoded_like_the_contract_abi() -> None:
    calls: list[dict[str, object]] = []
    root, head = h(1), h(2)

    def node(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        calls.append(body)
        data = bytes.fromhex(body["params"][0]["data"][2:])
        if data[:4] == selector("anchorOf(uint32)"):
            result = encode(
                ["(bytes32,bytes32,uint64,uint64,uint64,uint64)"], [(root, head, 5, 9, 4, 1_700_000_000)]
            )
        else:
            result = encode(["bool"], [True])
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": "0x" + result.hex()})

    chain = Chain("http://node", contract="0x" + "11" * 20, transport=httpx.MockTransport(node))
    assert await chain.anchor_of(491_000) == OnChainAnchor(root, head, 5, 9, 4, 1_700_000_000)
    assert await chain.verify_entry(491_000, 7, h(7), [h(8)]) is True
    assert calls[0]["method"] == "eth_call" and calls[0]["params"][0]["to"] == "0x" + "11" * 20  # type: ignore[index]

    failing = Chain("http://node", contract="0x" + "11" * 20, transport=httpx.MockTransport(
        lambda r: httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "error": {"message": "execution reverted"}})
    ))  # fmt: skip
    with pytest.raises(ChainError, match="execution reverted"):
        await failing.anchor_of(1)


# ---------------------------------------------------------------- the flow, against an in-memory contract


class FakeChain:
    """The contract's rules in Python: periods only move forward, ranges never overlap."""

    contract = "0x" + "aa" * 20

    def __init__(self) -> None:
        self.anchors: dict[int, OnChainAnchor] = {}
        self.sent = 0

    async def chain_id(self) -> int:
        return 31337

    async def anchor(
        self, period: int, root: bytes, head: bytes, first_id: int, last_id: int, entries: int
    ) -> Receipt:
        if self.anchors and (
            period <= max(self.anchors) or first_id <= max(a.last_id for a in self.anchors.values())
        ):
            raise ChainError("reverted")
        self.anchors[period] = OnChainAnchor(root, head, first_id, last_id, entries, 0)
        self.sent += 1
        return Receipt("0x" + f"{self.sent:064x}", self.sent)

    async def anchor_of(self, period: int) -> OnChainAnchor | None:
        return self.anchors.get(period)

    async def verify_entry(self, period: int, entry_id: int, entry_hash: bytes, proof: list[bytes]) -> bool:
        a = self.anchors.get(period)
        return bool(
            a and a.first_id <= entry_id <= a.last_id and merkle.verify(a.root, entry_id, entry_hash, proof)
        )


async def _log(n: int, at: datetime) -> None:
    async with db_session.sessions()() as session:
        for i in range(n):
            await audit.record(session, "test.event", "thing", i, data={"n": i}, at=at)
        await session.commit()


@pytest.mark.postgres
async def test_finished_periods_are_anchored_once_and_entries_prove(api: httpx.AsyncClient) -> None:
    chain = FakeChain()
    now = datetime(2026, 11, 7, 10, 30, tzinfo=UTC)
    await _log(5, now - timedelta(hours=2))
    await _log(3, now - timedelta(minutes=10))  # the current period: not yet
    async with db_session.sessions()() as session:
        first = await anchor_pending(session, chain, HOUR, now=now)
        assert first is not None and first.period == period_of(now, HOUR) - 1
        assert (first.entries, first.first_id, first.last_id) == (5, 1, 5)
        assert await anchor_pending(session, chain, HOUR, now=now) is None  # that period is done
        later = await anchor_pending(session, chain, HOUR, now=now + timedelta(hours=1))
        # the 3 entries of the next hour, and the audit entry about the first anchor
        assert later is not None and (later.first_id, later.entries) == (6, 4)

        for entry_id in (1, 3, 8):
            proof = await prove(session, chain, entry_id)
            assert proof is not None and proof.anchored and proof.verified_on_chain and proof.root_matches_log
        assert (await prove(session, chain, 999)) is None

        check = await check_all(session, chain)
        assert (check.anchors, check.matching, check.first_mismatch_period) == (2, 2, None)


@pytest.mark.postgres
async def test_rewriting_history_is_caught_even_with_a_valid_hash_chain(api: httpx.AsyncClient) -> None:
    chain = FakeChain()
    now = datetime(2026, 11, 7, 10, 30, tzinfo=UTC)
    await _log(6, now - timedelta(hours=2))
    async with db_session.sessions()() as session:
        anchored = await anchor_pending(session, chain, HOUR, now=now)
        assert anchored is not None

        # an insider changes entry 3 and recomputes every hash after it, so the log still verifies by itself
        await session.execute(update(AuditEntry).where(AuditEntry.id == 3).values(data={"n": "rewritten"}))
        previous = audit.GENESIS
        for row in (await session.execute(select(AuditEntry).order_by(AuditEntry.id))).scalars():
            row.prev_hash, row.hash = previous, audit.entry_hash(previous, audit._fields(row))
            previous = row.hash
        await session.commit()
        assert (await audit.verify(session)).valid  # the hash chain alone cannot tell

        check = await check_all(session, chain)
        assert check.first_mismatch_period == anchored.period  # the chain can
        proof = await prove(session, chain, 3)
        assert proof is not None and proof.root_matches_log is False and proof.verified_on_chain is False


@pytest.mark.postgres
async def test_an_anchor_sent_but_not_recorded_is_recovered_not_resent(api: httpx.AsyncClient) -> None:
    chain = FakeChain()
    now = datetime(2026, 11, 7, 10, 30, tzinfo=UTC)
    await _log(4, now - timedelta(hours=2))
    async with db_session.sessions()() as session:
        await anchor_pending(session, chain, HOUR, now=now)
        await session.rollback()
    async with db_session.sessions()() as session:  # as if the database write after the transaction failed
        await session.execute(AuditEntry.__table__.delete().where(AuditEntry.action == "audit.anchored"))
        from clearhire.db.models import Anchor

        await session.execute(Anchor.__table__.delete())
        await session.commit()
        recovered = await anchor_pending(session, chain, HOUR, now=now)
        assert recovered is not None and recovered.tx_hash == "" and chain.sent == 1


@pytest.mark.postgres
async def test_the_api_lists_anchors_and_proves_entries(api: httpx.AsyncClient) -> None:

    recruiter = await login(api, "recruiter")
    services = api._transport.app.state.services  # type: ignore[attr-defined]
    chain = FakeChain()
    services.chain = chain
    services.settings.anchor_contract = chain.contract
    await _log(3, datetime.now(UTC) - timedelta(hours=3))
    async with db_session.sessions()() as session:
        await anchor_pending(session, chain, HOUR)
    listed = (await api.get("/api/audit/anchors", headers=recruiter)).json()
    assert listed["enabled"] and listed["items"][0]["entries"] >= 3 and listed["unanchored"] >= 1
    proof = (await api.get("/api/audit/1/proof", headers=recruiter)).json()
    assert proof["verified_on_chain"] is True and proof["root_matches_chain"] is True
    assert (await api.get("/api/audit/anchors/check", headers=recruiter)).json()["matching"] == 1
    manager = await login(api, "manager")
    assert (await api.get("/api/audit/1/proof", headers=manager)).status_code == 403


# ---------------------------------------------------------------- the real contract, on Anvil

anvil = pytest.mark.skipif(
    not os.environ.get("ANVIL_URL"), reason="set ANVIL_URL to run against a real chain"
)


@anvil
@pytest.mark.postgres
async def test_on_a_real_chain(api: httpx.AsyncClient) -> None:
    chain = Chain(os.environ["ANVIL_URL"], ANVIL_KEY, poll=0.2)
    address, receipt = await chain.deploy(chain.address or "")
    assert address.startswith("0x") and receipt.block > 0
    now = datetime.now(UTC)
    await _log(9, now - timedelta(hours=2))
    async with db_session.sessions()() as session:
        anchored = await anchor_pending(session, chain, HOUR, now=now)
        assert anchored is not None and anchored.tx_hash.startswith("0x")
        on_chain = await chain.anchor_of(anchored.period)
        assert on_chain is not None and on_chain.root == anchored.root and on_chain.entries == 9
        for entry_id in (1, 5, 9):
            proof = await prove(session, chain, entry_id)
            assert proof is not None and proof.verified_on_chain is True
        assert (await check_all(session, chain)).matching == 1
        with pytest.raises(ChainError, match="revert"):  # the contract refuses to anchor that period again
            await chain.anchor(anchored.period, h(1), h(2), 100, 101, 2)
    await chain.close()
