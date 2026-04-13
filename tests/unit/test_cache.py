"""
Unit tests for the Redis cache layer.

Uses in-memory fallback (no Redis required).

Ref: AGENT.md Sprint 3.
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "services", "explainer"))

# Force in-memory mode (no Redis host)
os.environ.pop("REDIS_HOST", None)


class TestExplainerCache:
    def _make_cache(self):
        from redis_cache import ExplainerCache
        return ExplainerCache()

    def test_shap_set_and_get(self):
        cache = self._make_cache()
        payload = {"top_bias_drivers": [{"feature": "income", "importance": 0.45}]}

        cache.set_shap("audit-001", payload)
        result = cache.get_shap("audit-001")

        assert result == payload

    def test_shap_miss_returns_none(self):
        cache = self._make_cache()
        assert cache.get_shap("nonexistent-audit") is None

    def test_narrative_set_and_get(self):
        cache = self._make_cache()
        narrative = "## Bias Report\n\nModel shows CRITICAL bias."

        cache.set_narrative("audit-001", narrative)
        result = cache.get_narrative("audit-001")

        assert result == narrative

    def test_narrative_miss_returns_none(self):
        cache = self._make_cache()
        assert cache.get_narrative("nonexistent-audit") is None

    def test_report_set_and_get(self):
        cache = self._make_cache()
        fake_pdf = b"%PDF-1.4 fake pdf content"

        cache.set_report("model-v1", "2024-01-01", "2024-01-31", fake_pdf)
        result = cache.get_report("model-v1", "2024-01-01", "2024-01-31")

        assert result == fake_pdf

    def test_report_miss_returns_none(self):
        cache = self._make_cache()
        assert cache.get_report("unknown-model", "2024-01-01", "2024-01-31") is None

    def test_invalidate_clears_keys(self):
        cache = self._make_cache()
        cache.set_shap("audit-aaa", {"data": 1})
        cache.set_shap("audit-bbb", {"data": 2})

        n = cache.invalidate("shap:audit-aaa")
        assert n >= 1
        assert cache.get_shap("audit-aaa") is None
        # Other key should still be there
        assert cache.get_shap("audit-bbb") is not None

    def test_overwrite_existing_key(self):
        cache = self._make_cache()
        cache.set_shap("audit-001", {"version": 1})
        cache.set_shap("audit-001", {"version": 2})
        result = cache.get_shap("audit-001")
        assert result["version"] == 2


class TestGetCacheSingleton:
    def test_returns_same_instance(self):
        import redis_cache
        redis_cache._cache = None  # Reset singleton

        cache1 = redis_cache.get_cache()
        cache2 = redis_cache.get_cache()
        assert cache1 is cache2
