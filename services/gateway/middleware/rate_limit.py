"""
Gateway Middleware — Rate Limiting.

Redis-based rate limiting.
Predictions ingest: 10,000 req/min.
Other endpoints: 1,000 req/min.

Ref: AGENT.md Section 12.
"""

import os
import time
import logging
from collections import defaultdict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("fairops.gateway.rate_limit")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware.

    In production: uses Redis (Memorystore) for distributed rate limiting.
    In local dev: uses in-memory counter (single process only).
    """

    # Rate limits per endpoint pattern
    LIMITS = {
        "/v1/predictions/ingest": 10_000,  # 10k req/min
        "default": 1_000,                   # 1k req/min for other endpoints
    }

    def __init__(self, app):
        super().__init__(app)
        self._redis = None
        self._local_counters: dict[str, list] = defaultdict(list)
        self._init_redis()

    def _init_redis(self):
        """Try to connect to Redis. Fall back to in-memory if unavailable."""
        redis_host = os.environ.get("REDIS_HOST")
        if redis_host:
            try:
                import redis

                self._redis = redis.Redis(
                    host=redis_host,
                    port=int(os.environ.get("REDIS_PORT", "6379")),
                    decode_responses=True,
                )
                self._redis.ping()
                logger.info(f"Rate limiter connected to Redis at {redis_host}")
            except Exception as e:
                logger.warning(f"Redis unavailable, using in-memory rate limiter: {e}")
                self._redis = None

    def _get_limit(self, path: str) -> int:
        """Get the rate limit for a given path."""
        for pattern, limit in self.LIMITS.items():
            if pattern != "default" and path.startswith(pattern):
                return limit
        return self.LIMITS["default"]

    def _check_rate_limit_local(self, key: str, limit: int) -> bool:
        """Check rate limit using in-memory counters."""
        now = time.time()
        window_start = now - 60  # 1 minute window

        # Clean up old entries
        self._local_counters[key] = [
            ts for ts in self._local_counters[key] if ts > window_start
        ]

        if len(self._local_counters[key]) >= limit:
            return False

        self._local_counters[key].append(now)
        return True

    def _check_rate_limit_redis(self, key: str, limit: int) -> bool:
        """Check rate limit using Redis sliding window."""
        now = time.time()
        window_start = now - 60
        redis_key = f"fairops:ratelimit:{key}"

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(redis_key, 0, window_start)
        pipe.zadd(redis_key, {str(now): now})
        pipe.zcard(redis_key)
        pipe.expire(redis_key, 120)
        results = pipe.execute()

        current_count = results[2]
        return current_count <= limit

    async def dispatch(self, request: Request, call_next):
        # Skip rate limiting for health checks
        if request.url.path in ("/health", "/"):
            return await call_next(request)

        # Build rate limit key from client IP + path
        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        key = f"{client_ip}:{path}"

        limit = self._get_limit(path)

        # Check rate limit
        if self._redis:
            allowed = self._check_rate_limit_redis(key, limit)
        else:
            allowed = self._check_rate_limit_local(key, limit)

        if not allowed:
            logger.warning(
                f"Rate limit exceeded: {key}",
                extra={"client_ip": client_ip, "path": path, "limit": limit},
            )
            return JSONResponse(
                status_code=429,
                content={
                    "status": "error",
                    "error": {
                        "type": "RateLimitExceeded",
                        "message": f"Rate limit exceeded: {limit} requests per minute",
                    },
                },
                headers={"Retry-After": "60"},
            )

        return await call_next(request)
