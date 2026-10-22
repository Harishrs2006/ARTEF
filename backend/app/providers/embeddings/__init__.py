from abc import ABC, abstractmethod

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.config import get_settings
from app.core.logging import get_logger

settings = get_settings()
logger = get_logger(__name__)


class EmbeddingProvider(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        pass

    @abstractmethod
    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        pass

    async def close(self) -> None:
        return None


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, model: str, api_key: str, base_url: str = "", timeout: float = 30.0):
        if not api_key or not api_key.strip():
            raise ValueError(
                "No API key configured for the embedding provider. "
                "Set EMBEDDING_API_KEY in the environment."
            )
        self.model = model
        self.api_key = api_key.strip()
        self.base_url = (base_url or "https://api.openai.com/v1").rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=httpx.Timeout(timeout, connect=min(10.0, timeout)),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True,
    )
    async def _post(self, payload: dict) -> list[list[float]]:
        try:
            response = await self.client.post("/embeddings", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException:
            logger.error("embedding_provider_timeout", model=self.model)
            raise
        except httpx.HTTPStatusError as e:
            logger.error(
                "embedding_provider_http_error", model=self.model, status=e.response.status_code
            )
            raise
        except (ValueError, KeyError, IndexError, TypeError) as e:
            logger.error("embedding_provider_malformed_response", model=self.model)
            raise ValueError(f"Embedding provider returned a malformed response: {e}") from e

        try:
            return [item["embedding"] for item in data["data"]]
        except (KeyError, IndexError, TypeError) as e:
            raise ValueError(f"Embedding provider response is missing embeddings: {e}") from e

    async def embed(self, text: str) -> list[float]:
        vectors = await self._post({"model": self.model, "input": text})
        if not vectors:
            raise ValueError("Embedding provider returned no vectors")
        return vectors[0]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return await self._post({"model": self.model, "input": texts})

    async def close(self):
        await self.client.aclose()


class AnthropicEmbeddingProvider(EmbeddingProvider):
    """Anthropic does not expose an embeddings endpoint.

    Returning a zero vector silently would corrupt every similarity search, so
    the provider refuses to operate instead.
    """

    def __init__(self, model: str, api_key: str, base_url: str = ""):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url

    async def embed(self, text: str) -> list[float]:
        raise ValueError(
            "Anthropic does not provide an embeddings API. Configure "
            "EMBEDDING_PROVIDER=openai or a local mock provider."
        )

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        raise ValueError(
            "Anthropic does not provide an embeddings API. Configure "
            "EMBEDDING_PROVIDER=openai or a local mock provider."
        )


class MockEmbeddingProvider(EmbeddingProvider):
    """Deterministic, dependency-free embeddings for the local evaluation mode."""

    def __init__(self, dimension: int = 1536):
        self.dimension = dimension

    async def embed(self, text: str) -> list[float]:
        import hashlib

        digest = hashlib.sha256(text.encode("utf-8")).digest()
        # Expand the digest into a deterministic float vector.
        raw = int.from_bytes(digest * (self.dimension // len(digest) + 1), "big")
        return [((raw >> i) & 0xFFFF) / 65535.0 - 0.5 for i in range(self.dimension)]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [await self.embed(text) for text in texts]


class EmbeddingProviderFactory:
    @staticmethod
    def create_provider(
        provider: str, model: str, api_key: str, base_url: str = ""
    ) -> EmbeddingProvider:
        provider = (provider or "").lower()
        if provider == "openai":
            return OpenAIEmbeddingProvider(model, api_key, base_url)
        if provider == "anthropic":
            return AnthropicEmbeddingProvider(model, api_key, base_url)
        if provider == "mock" or settings.EVAL_MODE == "local":
            return MockEmbeddingProvider()
        logger.error("unknown_embedding_provider", provider=provider, model=model)
        raise ValueError(
            f"Unknown embedding provider '{provider}'. Supported providers: openai, mock."
        )


__all__ = [
    "AnthropicEmbeddingProvider",
    "EmbeddingProvider",
    "EmbeddingProviderFactory",
    "MockEmbeddingProvider",
    "OpenAIEmbeddingProvider",
]
