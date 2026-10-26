"""Unit tests for the mock embedding backend.

Contract (docs/build_docs/04-core-engine-specs.md section 5.3; the departure
record in docs/handover_docs/02-engine-conventions.md): deterministic vectors
behind the same interface as the future Ollama backend, tagged
`embedding_model: "mock"`, query and document embeddings from the same model.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from seeker.embeddings.mock import MockEmbeddingBackend


def run(coro):
    """Run an async backend call from sync tests."""
    return asyncio.run(coro)


def cosine(a: list[float], b: list[float]) -> float:
    na = math.sqrt(sum(v * v for v in a))
    nb = math.sqrt(sum(v * v for v in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)


class TestInterface:
    def test_model_name_is_mock(self) -> None:
        assert MockEmbeddingBackend().model_name == "mock"

    def test_default_dimensions_match_nomic(self) -> None:
        # nomic-embed-text is 768-dim; the store must be exercised at that size.
        assert MockEmbeddingBackend().dimensions == 768

    def test_custom_dimensions_are_respected(self) -> None:
        backend = MockEmbeddingBackend(dimensions=64)
        vector = run(backend.embed_query("hello world"))
        assert len(vector) == 64

    @pytest.mark.parametrize("bad", [0, -7])
    def test_nonpositive_dimensions_raise(self, bad: int) -> None:
        with pytest.raises(ValueError):
            MockEmbeddingBackend(dimensions=bad)


class TestDeterminism:
    def test_same_text_yields_identical_vectors(self) -> None:
        backend = MockEmbeddingBackend()
        first = run(backend.embed_query("quarterly budget disagreement"))
        second = run(backend.embed_query("quarterly budget disagreement"))
        assert first == second

    def test_identical_across_instances(self) -> None:
        # Determinism must not depend on instance state or call ordering.
        first = run(MockEmbeddingBackend().embed_query("a shared sentence"))
        second = run(MockEmbeddingBackend().embed_query("a shared sentence"))
        assert first == second

    def test_query_and_document_paths_agree(self) -> None:
        # The mock treats queries and passages identically; the pipeline may
        # rely on that symmetry until a real backend distinguishes them.
        backend = MockEmbeddingBackend()
        assert run(backend.embed_query("same text")) == run(
            backend.embed_documents(["same text"])
        )[0]

    def test_different_text_yields_different_vector(self) -> None:
        backend = MockEmbeddingBackend()
        assert run(backend.embed_query("cat")) != run(backend.embed_query("dog"))


class TestVectorShape:
    def test_nonempty_text_yields_unit_vector(self) -> None:
        vector = run(MockEmbeddingBackend().embed_query("some words here"))
        assert math.sqrt(sum(v * v for v in vector)) == pytest.approx(1.0)

    def test_empty_text_yields_zero_vector(self) -> None:
        vector = run(MockEmbeddingBackend().embed_query(""))
        assert vector == [0.0] * 768

    def test_batch_matches_input_length_and_order(self) -> None:
        backend = MockEmbeddingBackend()
        texts = ["alpha beta", "gamma delta", "alpha beta"]
        vectors = run(backend.embed_documents(texts))
        assert len(vectors) == len(texts)
        assert vectors[0] == vectors[2]
        assert vectors[0] != vectors[1]


class TestLexicalBehaviour:
    def test_identical_texts_score_one(self) -> None:
        backend = MockEmbeddingBackend()
        a = run(backend.embed_query("the quarterly budget disagreement"))
        b = run(backend.embed_documents(["the quarterly budget disagreement"]))[0]
        assert cosine(a, b) == pytest.approx(1.0)

    def test_shared_vocabulary_outranks_unrelated_text(self) -> None:
        # The property that makes the mock useful to the query pipeline: a
        # query ranks a text sharing its words above one sharing none.
        backend = MockEmbeddingBackend()
        query = run(backend.embed_query("quarterly budget disagreement"))
        near = run(backend.embed_documents(["the quarterly budget dispute between teams"]))[0]
        far = run(backend.embed_documents(["recipe for sourdough bread with flour"]))[0]
        assert cosine(query, near) > cosine(query, far)
