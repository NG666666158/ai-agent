from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import NAMESPACE_URL, uuid5

import httpx

from orion_agent.core.config import Settings
from orion_agent.core.models import LongTermMemoryRecord
from orion_agent.core.repository import TaskRepository


class BaseVectorStore(ABC):
  backend: str = "local"

  @abstractmethod
  def upsert(self, record: LongTermMemoryRecord) -> None:
    raise NotImplementedError

  @abstractmethod
  def search(self, query_embedding: list[float], scope: str, limit: int = 5) -> list[str]:
    raise NotImplementedError

  @abstractmethod
  def health(self) -> dict[str, str]:
    raise NotImplementedError


class LocalVectorStore(BaseVectorStore):
  backend = "local"

  def __init__(self, repository: TaskRepository) -> None:
    self.repository = repository

  def upsert(self, record: LongTermMemoryRecord) -> None:
    return None

  def search(self, query_embedding: list[float], scope: str, limit: int = 5) -> list[str]:
    records = self.repository.search_long_term_memories_by_vector(
      query_embedding=query_embedding,
      scope=scope,
      limit=limit,
    )
    return [record.id for record in records]

  def health(self) -> dict[str, str]:
    return {"backend": self.backend, "status": "ready"}


class QdrantVectorStore(BaseVectorStore):
  backend = "qdrant"

  def __init__(self, settings: Settings, fallback: BaseVectorStore) -> None:
    self.url = settings.vector_service_url.rstrip("/")
    self.collection = settings.vector_collection
    self.timeout = settings.vector_timeout
    self.api_key = settings.vector_api_key
    self.dimensions = settings.vector_dimensions
    self.fallback = fallback
    self._degraded = False
    self._collection_checked = False

  def _headers(self) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if self.api_key:
      headers["api-key"] = self.api_key
    return headers

  def _ensure_collection(self) -> None:
    if self._collection_checked or self._degraded:
      return
    payload = {
      "vectors": {
        "size": self.dimensions,
        "distance": "Cosine",
      }
    }
    try:
      response = httpx.put(
        f"{self.url}/collections/{self.collection}",
        headers=self._headers(),
        json=payload,
        timeout=self.timeout,
      )
      if response.status_code not in {200, 201, 409}:
        response.raise_for_status()
      self._collection_checked = True
    except Exception:
      self._degraded = True

  def upsert(self, record: LongTermMemoryRecord) -> None:
    if self._degraded:
      self.fallback.upsert(record)
      return
    self._ensure_collection()
    if self._degraded:
      self.fallback.upsert(record)
      return
    payload = {
      "points": [
        {
          "id": str(uuid5(NAMESPACE_URL, record.id)),
          "vector": record.embedding,
          "payload": {
            "memory_id": record.id,
            "scope": record.scope,
            "topic": record.topic,
            "created_at": record.created_at.isoformat(),
          },
        }
      ]
    }
    try:
      response = httpx.put(
        f"{self.url}/collections/{self.collection}/points?wait=true",
        headers=self._headers(),
        json=payload,
        timeout=self.timeout,
      )
      response.raise_for_status()
    except Exception:
      self._degraded = True
      self.fallback.upsert(record)

  def search(self, query_embedding: list[float], scope: str, limit: int = 5) -> list[str]:
    if self._degraded:
      return self.fallback.search(query_embedding=query_embedding, scope=scope, limit=limit)
    self._ensure_collection()
    if self._degraded:
      return self.fallback.search(query_embedding=query_embedding, scope=scope, limit=limit)
    payload = {
      "vector": query_embedding,
      "limit": limit,
      "with_payload": True,
      "filter": {
        "must": [
          {
            "key": "scope",
            "match": {"value": scope},
          }
        ]
      },
    }
    try:
      response = httpx.post(
        f"{self.url}/collections/{self.collection}/points/search",
        headers=self._headers(),
        json=payload,
        timeout=self.timeout,
      )
      response.raise_for_status()
      result = response.json().get("result", [])
      resolved_ids: list[str] = []
      for item in result:
        payload = item.get("payload") or {}
        resolved_ids.append(str(payload.get("memory_id") or item["id"]))
      return resolved_ids
    except Exception:
      self._degraded = True
      return self.fallback.search(query_embedding=query_embedding, scope=scope, limit=limit)

  def health(self) -> dict[str, str]:
    if self._degraded:
      return {"backend": self.backend, "status": "degraded"}
    try:
      response = httpx.get(f"{self.url}/readyz", headers=self._headers(), timeout=self.timeout)
      response.raise_for_status()
      return {"backend": self.backend, "status": "ready"}
    except Exception:
      self._degraded = True
      return {"backend": self.backend, "status": "degraded"}


def build_vector_store(settings: Settings, repository: TaskRepository) -> BaseVectorStore:
  fallback = LocalVectorStore(repository)
  if settings.vector_backend.lower() != "qdrant":
    return fallback
  return QdrantVectorStore(settings, fallback=fallback)
