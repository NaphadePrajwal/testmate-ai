import math
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings
from app.services.embedding_service import (
    EmbeddingConfigurationError,
    EmbeddingGenerationError,
    EmbeddingInputError,
    EmbeddingService,
    clear_model_cache,
    get_cached_sentence_transformer,
)


class DummySentenceTransformer:
    """Deterministic test double that generates normalized 384-d vectors without downloading model weights."""

    def __init__(self, model_name: str = "mock-model", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device

    def encode(
        self,
        sentences: str | list[str],
        batch_size: int = 32,
        normalize_embeddings: bool = True,
        convert_to_numpy: bool = True,
    ) -> Any:
        # If single sentence is passed
        if isinstance(sentences, str):
            val = 1.0 / math.sqrt(384)
            return [val] * 384

        # If list of sentences
        results = []
        for i, _ in enumerate(sentences):
            val = (i + 1.0) / math.sqrt(384)
            results.append([val] * 384)
        return results


@pytest.fixture(autouse=True)
def clean_cache() -> None:
    clear_model_cache()
    yield
    clear_model_cache()


def test_single_text_embedding_generation() -> None:
    """Verify single-text embedding returns 384 finite floats using the injected test double."""
    dummy_model = DummySentenceTransformer()
    service = EmbeddingService(model=dummy_model)

    vector = service.embed_text("Login button does not respond on click")
    assert isinstance(vector, list)
    assert len(vector) == 384
    assert all(isinstance(x, float) for x in vector)
    assert all(math.isfinite(x) for x in vector)


def test_batch_embedding_generation() -> None:
    """Verify batch embedding returns correctly structured vectors for all input items."""
    dummy_model = DummySentenceTransformer()
    service = EmbeddingService(model=dummy_model)

    texts = [
        "First automated failure: 404 Not Found",
        "Second failure: Element not interactable",
        "Third failure: Assertion error on response payload",
    ]
    vectors = service.embed_batch(texts)
    assert len(vectors) == 3
    for vec in vectors:
        assert len(vec) == 384
        assert all(math.isfinite(x) for x in vec)


def test_invalid_and_empty_text_inputs() -> None:
    """Ensure empty or whitespace-only inputs are rejected with EmbeddingInputError."""
    service = EmbeddingService(model=DummySentenceTransformer())

    with pytest.raises(EmbeddingInputError, match="cannot be empty or whitespace-only"):
        service.embed_text("")

    with pytest.raises(EmbeddingInputError, match="cannot be empty or whitespace-only"):
        service.embed_text("   \n\t  ")

    with pytest.raises(EmbeddingInputError, match="cannot be empty or whitespace-only"):
        service.embed_text(None)  # type: ignore[arg-type]


def test_invalid_batch_inputs() -> None:
    """Ensure empty batch or batches with invalid elements are rejected."""
    service = EmbeddingService(model=DummySentenceTransformer())

    with pytest.raises(EmbeddingInputError, match="must be a non-empty list"):
        service.embed_batch([])

    with pytest.raises(EmbeddingInputError, match="Batch item at index 1 cannot be empty"):
        service.embed_batch(["Valid text", "   ", "Another valid text"])

    with pytest.raises(EmbeddingInputError, match="Batch item at index 0 cannot be empty"):
        service.embed_batch([12345])  # type: ignore[list-item]


def test_dimension_mismatch_error() -> None:
    """Ensure dimension mismatch raises EmbeddingGenerationError."""
    mock_model = MagicMock()
    # Mock returns a vector with 512 dimensions instead of expected 384
    mock_model.encode.return_value = [0.1] * 512

    service = EmbeddingService(model=mock_model)
    with pytest.raises(EmbeddingGenerationError, match="dimension.*does not match expected dimension.*384"):
        service.embed_text("Test query")


def test_batch_dimension_mismatch_error() -> None:
    """Ensure batch dimension mismatch at any index raises EmbeddingGenerationError."""
    mock_model = MagicMock()
    # First vector 384, second vector 128
    mock_model.encode.return_value = [[0.1] * 384, [0.1] * 128]

    service = EmbeddingService(model=mock_model)
    with pytest.raises(EmbeddingGenerationError, match="Batch embedding at index 1 dimension"):
        service.embed_batch(["text1", "text2"])


def test_non_finite_embedding_error() -> None:
    """Ensure non-finite numerical values (NaN / Inf) are caught and rejected."""
    mock_model = MagicMock()
    bad_vector = [0.1] * 383 + [float("nan")]
    mock_model.encode.return_value = bad_vector

    service = EmbeddingService(model=mock_model)
    with pytest.raises(EmbeddingGenerationError, match="non-finite numerical values"):
        service.embed_text("Test text")


def test_model_encoding_exception_handling() -> None:
    """Ensure underlying encoding exceptions are converted to EmbeddingGenerationError."""
    mock_model = MagicMock()
    mock_model.encode.side_effect = RuntimeError("CUDA/Hardware failure")

    service = EmbeddingService(model=mock_model)
    with pytest.raises(EmbeddingGenerationError, match="Failed to generate embedding"):
        service.embed_text("Test text")


def test_model_loading_and_caching() -> None:
    """Verify that get_cached_sentence_transformer caches and reuses the loaded model instance."""
    mock_instance = MagicMock()
    with patch("sentence_transformers.SentenceTransformer", return_value=mock_instance) as mock_st_class:
        service1 = EmbeddingService()
        model1 = service1.model
        assert model1 is mock_instance

        # Second service instance accessing the same model name and device
        service2 = EmbeddingService()
        model2 = service2.model
        assert model2 is mock_instance

        # SentenceTransformer constructor should only be called once
        assert mock_st_class.call_count == 1


def test_model_initialization_failure() -> None:
    """Verify model loading failures raise EmbeddingConfigurationError."""
    with patch("sentence_transformers.SentenceTransformer", side_effect=Exception("Weights not found")):
        service = EmbeddingService()
        with pytest.raises(EmbeddingConfigurationError, match="Failed to load embedding model"):
            _ = service.model


def test_settings_dimension_consistency_validation() -> None:
    """Verify Settings rejects configuration where embedding dimension != qdrant_vector_size."""
    with pytest.raises(ValueError, match="Configuration mismatch: embedding_dimension.*must equal qdrant_vector_size"):
        Settings(
            embedding_dimension=512,
            qdrant_vector_size=384,
        )
