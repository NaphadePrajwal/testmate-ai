import logging
import math
import threading
from typing import Any

from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Module-level thread-safe cache for loaded SentenceTransformer model instances
_MODEL_CACHE: dict[tuple[str, str], Any] = {}
_CACHE_LOCK = threading.Lock()


class EmbeddingError(Exception):
    """Base exception for all embedding operations."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised when the embedding model configuration is invalid or cannot be initialized."""


class EmbeddingInputError(EmbeddingError):
    """Raised when text input provided for embedding is empty, whitespace-only, or invalid."""


class EmbeddingGenerationError(EmbeddingError):
    """Raised when the model fails to generate an embedding or returns unexpected dimensions."""


def get_cached_sentence_transformer(model_name: str, device: str) -> Any:
    """
    Retrieve or load a SentenceTransformer model instance from cache in a thread-safe manner.
    Reuses the in-memory model weights across requests rather than reloading per call.
    """
    cache_key = (model_name, device)
    with _CACHE_LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]

        try:
            from sentence_transformers import SentenceTransformer

            logger.info("Loading SentenceTransformer model '%s' on device '%s'...", model_name, device)
            model_instance = SentenceTransformer(model_name, device=device)
            _MODEL_CACHE[cache_key] = model_instance
            logger.info("Successfully loaded SentenceTransformer model '%s'.", model_name)
            return model_instance
        except Exception as exc:
            logger.error("Failed to load SentenceTransformer model '%s': %s", model_name, exc)
            raise EmbeddingConfigurationError(
                f"Failed to load embedding model '{model_name}': {exc}"
            ) from exc


def clear_model_cache() -> None:
    """Clear all cached SentenceTransformer instances (primarily used in test teardown)."""
    with _CACHE_LOCK:
        _MODEL_CACHE.clear()


class EmbeddingService:
    """
    Service responsible for converting historical bug descriptions, test cases,
    failure analyses, and search queries into numerical vector embeddings compatible with Qdrant.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        model: Any | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.model_name = self.settings.embedding_model
        self.expected_dimension = self.settings.embedding_dimension
        self.device = self.settings.embedding_device
        self.batch_size = self.settings.embedding_batch_size
        self._model = model

    @property
    def model(self) -> Any:
        """Lazily access or load the underlying SentenceTransformer model instance."""
        if self._model is None:
            self._model = get_cached_sentence_transformer(self.model_name, self.device)
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """
        Generate a normalized numerical embedding vector for a single string.

        Args:
            text: Non-empty string to embed.

        Returns:
            A list of floats with length equal to expected_dimension (384).

        Raises:
            EmbeddingInputError: If text is empty, whitespace-only, or not a string.
            EmbeddingGenerationError: If generation fails, returns non-finite values, or dimension mismatches.
        """
        if not isinstance(text, str) or not text.strip():
            raise EmbeddingInputError("Embedding input text cannot be empty or whitespace-only.")

        try:
            # normalize_embeddings=True produces unit vectors for Cosine distance in Qdrant
            raw_vector = self.model.encode(
                text.strip(),
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as exc:
            logger.error("Model encoding failure for text: %s", exc)
            raise EmbeddingGenerationError(f"Failed to generate embedding: {exc}") from exc

        vector = [float(val) for val in raw_vector]

        if len(vector) != self.expected_dimension:
            raise EmbeddingGenerationError(
                f"Generated embedding dimension ({len(vector)}) does not match expected dimension "
                f"({self.expected_dimension}) for model '{self.model_name}'."
            )

        if not all(math.isfinite(val) for val in vector):
            raise EmbeddingGenerationError("Generated embedding contains non-finite numerical values (NaN or Inf).")

        return vector

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate normalized numerical embedding vectors for a batch of strings.

        Args:
            texts: Non-empty list of non-empty strings.

        Returns:
            A list of vector lists, each of length expected_dimension (384).

        Raises:
            EmbeddingInputError: If texts is empty or contains non-string or whitespace-only elements.
            EmbeddingGenerationError: If generation fails or output dimensions are incorrect.
        """
        if not isinstance(texts, list) or len(texts) == 0:
            raise EmbeddingInputError("Batch input must be a non-empty list of strings.")

        cleaned_texts: list[str] = []
        for index, item in enumerate(texts):
            if not isinstance(item, str) or not item.strip():
                raise EmbeddingInputError(
                    f"Batch item at index {index} cannot be empty or whitespace-only."
                )
            cleaned_texts.append(item.strip())

        try:
            raw_vectors = self.model.encode(
                cleaned_texts,
                batch_size=self.batch_size,
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as exc:
            logger.error("Batch encoding failure for %d texts: %s", len(cleaned_texts), exc)
            raise EmbeddingGenerationError(f"Failed to generate batch embeddings: {exc}") from exc

        results: list[list[float]] = []
        for index, raw_vec in enumerate(raw_vectors):
            vec = [float(val) for val in raw_vec]
            if len(vec) != self.expected_dimension:
                raise EmbeddingGenerationError(
                    f"Batch embedding at index {index} dimension ({len(vec)}) does not match "
                    f"expected dimension ({self.expected_dimension})."
                )
            if not all(math.isfinite(val) for val in vec):
                raise EmbeddingGenerationError(
                    f"Batch embedding at index {index} contains non-finite numerical values (NaN or Inf)."
                )
            results.append(vec)

        return results
