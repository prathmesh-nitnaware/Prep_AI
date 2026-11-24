"""
backend/utils/rate_limiter.py
=============================
Pluggable Rate Limiter Abstraction Layer for PrepAI.
Supports InMemoryRateLimiterBackend (default token-bucket) and prepared for Redis.
Accurately documents that in-memory mode is per-instance, while Redis is globally distributed.
"""
import os
import time
import logging
import threading
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any, Dict

logger = logging.getLogger(__name__)


class RateLimiterBackend(ABC):
    """Abstract base class for rate limiting engines."""

    @abstractmethod
    def is_allowed(self, key: str) -> bool:
        """Determines if a request for the given key (e.g. IP or user_id) is permitted."""
        pass

    @abstractmethod
    def remaining(self, key: str) -> int:
        """Returns the number of remaining permitted requests for the key."""
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Returns rate limiter operational statistics."""
        pass


class InMemoryRateLimiterBackend(RateLimiterBackend):
    """
    Token-Bucket rate limiter maintained strictly per Python process/instance.

    Arithmetic & Concurrency Model:
      - Initial Bucket Capacity: `capacity` (default 60 tokens).
      - Burst Allowance: Exactly 60 requests per worker process before throttling.
      - Refill Rate: `refill_rate` (default 15.0 tokens per SECOND, not per minute).
      - Sustained Throughput: 15 requests/second (900 requests/minute) per worker process.
      - First-Minute Ceiling: 60 (initial burst) + 15 * 60 (refill) = 960 requests per process.

    Process-Local Isolation & Multi-Worker Aggregate Bounds:
      - In multi-process deployments (e.g. 3 Docker containers x 2 Gunicorn workers = 6 workers),
        each process maintains an independent in-memory bucket store.
      - State is process-local and is NOT globally synchronized across worker processes.
      - Aggregate cluster metrics (e.g. theoretical burst ceiling of 360 requests and sustained
        90 req/s across 6 workers) represent theoretical mathematical upper bounds under
        ideal round-robin distribution, NOT guaranteed throughput.
      - If trusted proxy headers are missing or malformed and requests fall back to an internal
        proxy IP, distinct users will collide on the fallback IP and share a single bucket.
      - Code-level support for 'nginx' or 'render' proxy strategies does not imply that those
        configurations are actively enabled in the live environment without explicit environment configuration.
    """

    def __init__(self, capacity: int = 60, refill_rate: float = 15.0):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._buckets: Dict[str, Dict[str, Any]] = defaultdict(self._new_bucket)
        self._lock = threading.Lock()

    def _new_bucket(self) -> Dict[str, Any]:
        return {"tokens": float(self._capacity), "last_refill": time.monotonic()}

    def _refill(self, bucket: Dict[str, Any]) -> None:
        now = time.monotonic()
        delta = now - bucket["last_refill"]
        bucket["tokens"] = min(
            float(self._capacity),
            bucket["tokens"] + delta * self._refill_rate
        )
        bucket["last_refill"] = now

    def is_allowed(self, key: str) -> bool:
        with self._lock:
            bucket = self._buckets[key]
            self._refill(bucket)
            if bucket["tokens"] >= 1.0:
                bucket["tokens"] -= 1.0
                return True
            return False

    def remaining(self, key: str) -> int:
        with self._lock:
            bucket = self._buckets[key]
            self._refill(bucket)
            return max(0, int(bucket["tokens"]))

    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "backend": "memory",
                "active_keys": len(self._buckets),
                "capacity": self._capacity,
                "refill_rate": self._refill_rate,
                "is_distributed": False,
                "scope_note": "Rate limits are process-local and enforced independently per Gunicorn worker process.",
            }


class RedisRateLimiterBackend(RateLimiterBackend):
    """
    Distributed Redis-backed rate limiter for shared cluster limits.
    Falls back to in-memory if Redis is unavailable.
    """

    def __init__(self, redis_url: str, capacity: int = 60, refill_rate: float = 15.0):
        self.redis_url = redis_url
        self.capacity = capacity
        self.refill_rate = refill_rate
        self._allow_fallback = os.getenv("REDIS_ALLOW_FALLBACK", "false").lower() == "true"
        self._memory_fallback = InMemoryRateLimiterBackend(capacity, refill_rate)
        self._client = None

        try:
            import redis
            self._client = redis.from_url(redis_url, decode_responses=True)
            self._client.ping()
            logger.info("Connected to distributed Redis rate limiter.")
        except Exception as e:
            if not self._allow_fallback:
                logger.error(f"Redis rate limiter connection failed: {e}. Set REDIS_ALLOW_FALLBACK=true to allow in-memory fallback.")
                raise RuntimeError(f"FATAL: Redis rate limiter unavailable and REDIS_ALLOW_FALLBACK is disabled: {e}")
            logger.warning(f"Redis rate limiter init failed: {e}. Falling back to in-memory.")
            self._client = None

    def is_allowed(self, key: str) -> bool:
        if not self._client:
            return self._memory_fallback.is_allowed(key)
        try:
            redis_key = f"ratelimit:{key}"
            current = self._client.incr(redis_key)
            if current == 1:
                self._client.expire(redis_key, 60)
            return current <= self.capacity
        except Exception as e:
            logger.warning(f"Redis rate limiter check error: {e}")
            return self._memory_fallback.is_allowed(key)

    def remaining(self, key: str) -> int:
        if not self._client:
            return self._memory_fallback.remaining(key)
        try:
            redis_key = f"ratelimit:{key}"
            val = self._client.get(redis_key)
            used = int(val) if val else 0
            return max(0, self.capacity - used)
        except Exception:
            return self._memory_fallback.remaining(key)

    def get_stats(self) -> Dict[str, Any]:
        return {
            "backend": "redis",
            "capacity": self.capacity,
            "refill_rate": self.refill_rate,
            "is_distributed": True,
            "scope_note": "Rate limits are globally shared across all backend replicas via Redis.",
        }


def create_rate_limiter_backend() -> RateLimiterBackend:
    """Factory to instantiate the configured rate limiter backend."""
    backend_type = os.getenv("RATE_LIMIT_BACKEND", "memory").lower().strip()
    redis_url = os.getenv("REDIS_URL")

    capacity = int(os.getenv("RATE_LIMIT_CAPACITY", "60"))
    refill_rate = float(os.getenv("RATE_LIMIT_REFILL_RATE", "15.0"))

    if backend_type == "redis" and redis_url:
        return RedisRateLimiterBackend(redis_url, capacity, refill_rate)
    return InMemoryRateLimiterBackend(capacity, refill_rate)


# Singleton rate limiter backend instance
default_rate_limiter = create_rate_limiter_backend()
