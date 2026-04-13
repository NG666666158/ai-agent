from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod

from openai import OpenAI

from orion_agent.core.config import Settings


class BaseEmbedder(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class HashingEmbedder(BaseEmbedder):
    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            sign = 1.0 if digest[2] % 2 == 0 else -1.0
            weight = ((digest[3] / 255.0) + 0.1) * sign
            vector[index] += weight
        return normalize(vector)


class OpenAIEmbedder(BaseEmbedder):
    def __init__(self, settings: Settings) -> None:
        self.client = OpenAI(api_key=settings.openai_api_key, max_retries=0)
        self.model = settings.embedding_model
        self.fallback = HashingEmbedder()
        self._degraded = False

    def embed(self, text: str) -> list[float]:
        if self._degraded:
            return self.fallback.embed(text)
        try:
            response = self.client.embeddings.create(model=self.model, input=text)
            return normalize(response.data[0].embedding)
        except Exception:
            self._degraded = True
            return self.fallback.embed(text)


def build_embedder(settings: Settings) -> BaseEmbedder:
    if settings.force_fallback_llm or not settings.openai_api_key:
        return HashingEmbedder()
    return OpenAIEmbedder(settings)


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b:
        return 0.0
    return sum(x * y for x, y in zip(a, b))


def normalize(values: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in values))
    if norm == 0:
        return values
    return [v / norm for v in values]
