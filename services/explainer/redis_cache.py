"""
FairOps Explainer — Redis Cache Layer.

Caches SHAP results and Gemini narratives for 1 hour.
Falls back to no-cache mode when Redis is unavailable.

Ref: AGENT.md Sprint 3.
"""

import json
import logging
import os
from typing import Any, Optional

logger = logging.getLogger("fairops.explainer.cache")

# Cache TTLs (seconds)
SHAP_TTL = 3600       # 1 hour
NARRATIVE_TTL = 3600  # 1 hour
REPORT_TTL = 86400    # 24 hours (PDF reports change less often)


class ExplainerCache:
    """
    Redis-backed cache for expensive compute results (SHAP, Gemini, reports).

    Falls back to in-memory dict when Redis is unavailable.
    """

    def __init__(self):
        self._redis = None
        self._memory_cache: dict[str, Any] = {}
        self._init_redis()

    def _init_redis(self):
        redis_host = os.environ.get("REDIS_HOST")
        if not redis_host:
            logger.info("REDIS_HOST not set — using in-memory cache (single-process only)")
            return

        try:
            import redis

            self._redis = redis.Redis(
                host=redis_host,
                port=int(os.environ.get("REDIS_PORT", "6379")),
                db=1,  # Separate DB from rate limiter
                decode_responses=True,
                socket_timeout=2,
                socket_connect_timeout=2,
            )
            self._redis.ping()
            logger.info(f"Cache connected to Redis at {redis_host}")
        except Exception as e:
            logger.warning(f"Redis unavailable ({e}) — using in-memory cache")
            self._redis = None

    # ── SHAP Cache ────────────────────────────────────────────────────────────

    def get_shap(self, audit_id: str) -> Optional[dict]:
        """Get cached SHAP result for an audit."""
        return self._get(f"shap:{audit_id}")

    def set_shap(self, audit_id: str, result: dict) -> None:
        """Cache SHAP result for 1 hour."""
        self._set(f"shap:{audit_id}", result, ttl=SHAP_TTL)

    # ── Narrative Cache ───────────────────────────────────────────────────────

    def get_narrative(self, audit_id: str) -> Optional[str]:
        """Get cached Gemini narrative for an audit."""
        return self._get(f"narrative:{audit_id}")

    def set_narrative(self, audit_id: str, narrative: str) -> None:
        """Cache Gemini narrative for 1 hour."""
        self._set(f"narrative:{audit_id}", narrative, ttl=NARRATIVE_TTL)

    # ── Report Cache ──────────────────────────────────────────────────────────

    def get_report(self, model_id: str, start_date: str, end_date: str) -> Optional[bytes]:
        """Get cached PDF compliance report bytes."""
        key = f"report:{model_id}:{start_date}:{end_date}"
        value = self._get(key)
        if value and isinstance(value, str):
            import base64
            return base64.b64decode(value)
        return None

    def set_report(self, model_id: str, start_date: str, end_date: str, pdf_bytes: bytes) -> None:
        """Cache PDF compliance report for 24 hours."""
        import base64
        key = f"report:{model_id}:{start_date}:{end_date}"
        self._set(key, base64.b64encode(pdf_bytes).decode(), ttl=REPORT_TTL)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _get(self, key: str) -> Optional[Any]:
        """Get value from Redis or memory cache."""
        if self._redis:
            try:
                raw = self._redis.get(f"fairops:explainer:{key}")
                if raw:
                    return json.loads(raw)
            except Exception as e:
                logger.warning(f"Cache GET failed for {key}: {e}")
        else:
            return self._memory_cache.get(key)
        return None

    def _set(self, key: str, value: Any, ttl: int = 3600) -> None:
        """Set value in Redis or memory cache with TTL."""
        full_key = f"fairops:explainer:{key}"

        if self._redis:
            try:
                self._redis.setex(full_key, ttl, json.dumps(value))
            except Exception as e:
                logger.warning(f"Cache SET failed for {key}: {e}")
                # Fall through to memory cache
                self._memory_cache[key] = value
        else:
            self._memory_cache[key] = value

    def invalidate(self, pattern: str) -> int:
        """Invalidate all cache keys matching a pattern."""
        if self._redis:
            try:
                keys = self._redis.keys(f"fairops:explainer:{pattern}*")
                if keys:
                    return self._redis.delete(*keys)
            except Exception as e:
                logger.warning(f"Cache invalidation failed: {e}")
        else:
            to_delete = [k for k in self._memory_cache if k.startswith(pattern)]
            for k in to_delete:
                del self._memory_cache[k]
            return len(to_delete)
        return 0


# Module-level singleton
_cache: Optional[ExplainerCache] = None


def get_cache() -> ExplainerCache:
    """Get or create the module-level cache singleton."""
    global _cache
    if _cache is None:
        _cache = ExplainerCache()
    return _cache
