"""Merkle trees over audit log entries, built exactly as contracts/src/AuditAnchor.sol checks them.

Leaf: keccak256(keccak256(id as uint64 || entry hash)), hashed twice so a leaf is never mistaken for an
inner node. Inner node: keccak256 of the two children in sorted order (OpenZeppelin's MerkleProof scheme),
so a proof is just the list of siblings. Levels are built pairwise from the left; a level's odd last node
is carried up unchanged. The contract test replays proofs written by this module (anchor-fixture).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from Crypto.Hash import keccak


def keccak256(data: bytes) -> bytes:
    return keccak.new(digest_bits=256, data=data).digest()


def leaf(entry_id: int, entry_hash: bytes) -> bytes:
    if len(entry_hash) != 32 or not 0 < entry_id < 2**64:
        raise ValueError("an entry is a positive 64-bit id and a 32-byte hash")
    return keccak256(keccak256(entry_id.to_bytes(8, "big") + entry_hash))


def hash_pair(a: bytes, b: bytes) -> bytes:
    return keccak256(a + b if a < b else b + a)


@dataclass(frozen=True)
class Tree:
    levels: list[list[bytes]]  # levels[0] are the leaves, levels[-1] == [root]

    @property
    def root(self) -> bytes:
        return self.levels[-1][0]

    def proof(self, index: int) -> list[bytes]:
        if not 0 <= index < len(self.levels[0]):
            raise IndexError(index)
        path = []
        for level in self.levels[:-1]:
            sibling = index ^ 1
            if sibling < len(level):
                path.append(level[sibling])
            index //= 2
        return path


def build(leaves: Sequence[bytes]) -> Tree:
    if not leaves:
        raise ValueError("a tree needs at least one leaf")
    levels = [list(leaves)]
    while len(levels[-1]) > 1:
        level = levels[-1]
        levels.append([hash_pair(level[i], level[i + 1]) if i + 1 < len(level) else level[i]
                       for i in range(0, len(level), 2)])  # fmt: skip
    return Tree(levels)


def verify(root: bytes, entry_id: int, entry_hash: bytes, proof: Sequence[bytes]) -> bool:
    node = leaf(entry_id, entry_hash)
    for sibling in proof:
        node = hash_pair(node, sibling)
    return node == root
