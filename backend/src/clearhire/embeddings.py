"""Text embedders: a multilingual sentence-transformers model, and a model-free hashing embedder for tests."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from functools import cache
from typing import Protocol

import numpy as np
import numpy.typing as npt

from clearhire.text import fold

Vectors = npt.NDArray[np.float32]
_WORD = re.compile(r"[^\W_]+")


class Embedder(Protocol):
    name: str
    dim: int

    def embed_queries(self, texts: Sequence[str]) -> Vectors: ...

    def embed_passages(self, texts: Sequence[str]) -> Vectors: ...


def default_prefixes(model_name: str) -> tuple[str, str]:
    """Instruction prefixes the model was trained with (E5 expects "query: " and "passage: ")."""
    name = model_name.lower()
    if "e5" in name and "instruct" not in name:
        return "query: ", "passage: "
    return "", ""


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str, *, device: str | None = None, batch_size: int = 32) -> None:
        from sentence_transformers import SentenceTransformer

        self.name = model_name
        self.model = SentenceTransformer(model_name, device=device)
        get_dimension = (  # renamed to get_embedding_dimension in sentence-transformers 6
            getattr(self.model, "get_embedding_dimension", None)
            or self.model.get_sentence_embedding_dimension
        )
        dim = get_dimension()
        if dim is None:
            raise ValueError(f"{model_name} does not report an embedding size")
        self.dim = int(dim)
        self.batch_size = batch_size
        self.query_prefix, self.passage_prefix = default_prefixes(model_name)

    def _encode(self, texts: Sequence[str]) -> Vectors:
        vectors = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.ascontiguousarray(vectors, dtype=np.float32)

    def embed_queries(self, texts: Sequence[str]) -> Vectors:
        return self._encode([self.query_prefix + text for text in texts])

    def embed_passages(self, texts: Sequence[str]) -> Vectors:
        return self._encode([self.passage_prefix + text for text in texts])


class HashEmbedder:
    """Signed feature hashing of words and character trigrams, L2-normalised.

    Lexical rather than semantic, but deterministic and instant: tests use it so they never load a model.
    """

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim
        self.name = f"hash-{dim}"

    def _embed(self, texts: Sequence[str]) -> Vectors:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            words = _WORD.findall(fold(text))
            features = [f"w:{w}" for w in words]
            for word in words:
                padded = f"#{word}#"
                features.extend(f"c:{padded[i : i + 3]}" for i in range(len(padded) - 2))
            for feature in features:
                value = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little")
                weight = 2.0 if feature.startswith("w:") else 1.0
                out[row, value % self.dim] += weight if value >> 63 else -weight
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms

    def embed_queries(self, texts: Sequence[str]) -> Vectors:
        return self._embed(texts)

    def embed_passages(self, texts: Sequence[str]) -> Vectors:
        return self._embed(texts)


@cache
def load_embedder(model_name: str, device: str | None = None) -> Embedder:
    if model_name == "hash" or model_name.startswith("hash-"):
        return HashEmbedder(int(model_name.split("-", 1)[1]) if "-" in model_name else 384)
    return SentenceTransformerEmbedder(model_name, device=device)
