"""A deterministic tree for the contract's test (contracts/test/fixtures/merkle.json), so the Solidity
verifier is checked against proofs this backend actually produces."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from clearhire.anchoring.merkle import build, leaf

FIRST_ID = 1001
COUNT = 13  # odd, so the tree carries a node up unpaired


def fixture() -> dict[str, object]:
    ids = [FIRST_ID + i * 2 if i % 4 else FIRST_ID + i * 2 + 1 for i in range(COUNT)]  # gaps, like a sequence
    hashes = [hashlib.sha256(f"audit entry {i}".encode()).digest() for i in range(COUNT)]
    leaves = [leaf(i, h) for i, h in zip(ids, hashes, strict=True)]
    tree = build(leaves)
    return {
        "root": "0x" + tree.root.hex(), "head": "0x" + hashes[-1].hex(),
        "first_id": ids[0], "last_id": ids[-1], "count": COUNT,
        "entries": [{"id": i, "hash": "0x" + h.hex(), "leaf": "0x" + lf.hex(),
                     "proof": ["0x" + p.hex() for p in tree.proof(k)]}
                    for k, (i, h, lf) in enumerate(zip(ids, hashes, leaves, strict=True))],
    }  # fmt: skip


def write(out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture(), indent=2) + "\n", encoding="utf-8")
