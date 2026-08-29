"""
Tests for provider abstraction layer: models, health, registry, router, and adapters.
"""
import pytest
import asyncio

from app.core.context import ExecutionContext, Actor, ActorType, Product, AgentMode
from app.providers.models import ProviderMeta, ProviderResult, ProviderError, ProviderStatus, AuthType
from app.providers.health import CircuitBreaker, CircuitState, ProviderHealth
from app.providers.registry import ProviderRegistry
from app.providers.base import BaseProvider
from app.providers.router import route, NoProviderAvailable

import app.tools.core.weather  # noqa: F401
import app.tools.core.currency  # noqa: F401
import app.tools.core.geo  # noqa: F401
import app.tools.core.phone  # noqa: F401
import app.tools.core.email_tool  # noqa: F401
import app.providers.adapters  # noqa: F401


def _make_ctx():
    return ExecutionContext(
        tenant_id="test",
        product=Product.QIAD,
        actor=Actor(type=ActorType.AGENT, id="test-agent"),
        agent_mode=AgentMode.AUTOPILOT,
    )


class DummyProvider(BaseProvider):
    def __init__(self, key="dummy", caps=None, priority=50, succeed=True):
        self._succeed = succeed
        self._meta = ProviderMeta(
            key=key,
            display_name=f"Dummy ({key})",
            capabilities=caps or ["test.action"],
            priority=priority,
        )

    def meta(self):
        return self._meta

    async def execute(self, capability, params, timeout=None):
        if self._succeed:
            return ProviderResult(
                provider=self._meta.key,
                capability=capability,
                status=ProviderStatus.SUCCESS,
                data={"echo": params},
            )
        return ProviderResult(
            provider=self._meta.key,
            capability=capability,
            status=ProviderStatus.ERROR,
            data={"error": "forced failure"},
        )

    async def health_check(self):
        return self._succeed


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.is_available("new_provider")
        h = cb.get_health("new_provider")
        assert h.state == CircuitState.CLOSED

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure("p1", 100)
        assert not cb.is_available("p1")
        h = cb.get_health("p1")
        assert h.state == CircuitState.OPEN

    def test_success_resets_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure("p1", 100)
        cb.record_failure("p1", 100)
        cb.record_success("p1", 50)
        cb.record_failure("p1", 100)
        assert cb.is_available("p1")

    def test_reset_clears_state(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure("p1", 100)
        cb.record_failure("p1", 100)
        assert not cb.is_available("p1")
        cb.reset("p1")
        assert cb.is_available("p1")

    def test_health_stats(self):
        cb = CircuitBreaker()
        cb.record_success("p1", 100)
        cb.record_success("p1", 200)
        cb.record_failure("p1", 300)
        h = cb.get_health("p1")
        assert h.success_count == 2
        assert h.failure_count == 1
        assert h.avg_latency_ms == 200.0
        assert round(h.failure_rate, 2) == 0.33

    def test_to_dict(self):
        cb = CircuitBreaker()
        cb.record_success("p1", 50)
        d = cb.get_health("p1").to_dict()
        assert "success_count" in d
        assert "failure_rate" in d
        assert d["state"] == "closed"


class TestProviderRegistry:
    def test_register_and_get(self):
        reg = ProviderRegistry()
        p = DummyProvider(key="test_reg")
        reg.register(p)
        assert reg.get("test_reg") is p

    def test_find_by_capability(self):
        reg = ProviderRegistry()
        reg.register(DummyProvider(key="a", caps=["geo.geocode"]))
        reg.register(DummyProvider(key="b", caps=["weather.current"]))
        reg.register(DummyProvider(key="c", caps=["geo.geocode", "weather.current"]))

        geo = reg.find_by_capability("geo.geocode")
        assert len(geo) == 2
        keys = {p.key for p in geo}
        assert keys == {"a", "c"}

    def test_disable_enable(self):
        reg = ProviderRegistry()
        reg.register(DummyProvider(key="d"))
        assert reg.disable("d")
        assert reg.find_by_capability("test.action") == []
        assert reg.enable("d")
        assert len(reg.find_by_capability("test.action")) == 1

    def test_list_all(self):
        reg = ProviderRegistry()
        reg.register(DummyProvider(key="x"))
        reg.register(DummyProvider(key="y"))
        assert len(reg.list_all()) == 2


class TestRouter:
    def test_no_provider_raises(self):
        from app.providers.registry import provider_registry as pr
        original = dict(pr._providers)
        pr._providers.clear()
        try:
            with pytest.raises(NoProviderAvailable):
                asyncio.run(route(_make_ctx(), "nonexistent.capability", {}))
        finally:
            pr._providers.update(original)


class TestModels:
    def test_provider_result_defaults(self):
        r = ProviderResult(provider="p", capability="c", status=ProviderStatus.SUCCESS)
        assert r.data == {}
        assert r.cached is False
        assert r.elapsed_ms == 0

    def test_provider_error_retryable(self):
        e = ProviderError(
            provider="p", capability="c",
            status=ProviderStatus.TIMEOUT, message="timeout",
        )
        assert e.is_retryable

        e2 = ProviderError(
            provider="p", capability="c",
            status=ProviderStatus.AUTH_FAILED, message="bad key",
        )
        assert not e2.is_retryable

    def test_provider_meta_fields(self):
        m = ProviderMeta(key="test", display_name="Test", capabilities=["a", "b"])
        assert m.enabled is True
        assert m.priority == 100
        assert m.auth_type == AuthType.API_KEY


from app.providers.registry import provider_registry


class TestAdapterRegistration:
    def test_open_meteo_registered(self):
        p = provider_registry.get("open_meteo")
        assert p is not None
        assert p.supports("weather.current")
        assert p.supports("weather.forecast")

    def test_exchangerate_registered(self):
        p = provider_registry.get("exchangerate_api")
        assert p is not None
        assert p.supports("currency.convert")

    def test_nominatim_registered(self):
        p = provider_registry.get("nominatim")
        assert p is not None
        assert p.supports("geo.geocode")
        assert p.supports("geo.reverse_geocode")

    def test_local_email_registered(self):
        p = provider_registry.get("local_email")
        assert p is not None
        assert p.supports("email.validate")

    def test_local_phone_registered(self):
        p = provider_registry.get("local_phone")
        assert p is not None
        assert p.supports("phone.validate")

    def test_local_phone_validate(self):
        p = provider_registry.get("local_phone")
        result = asyncio.run(p.execute("phone.validate", {
            "phone_number": "+966501234567", "country_code": "SA",
        }))
        assert result.status == ProviderStatus.SUCCESS
        assert result.data["valid"] is True

    def test_local_phone_invalid(self):
        p = provider_registry.get("local_phone")
        result = asyncio.run(p.execute("phone.validate", {
            "phone_number": "12", "country_code": "",
        }))
        assert result.status == ProviderStatus.SUCCESS
        assert result.data["valid"] is False

    def test_local_email_valid_format(self):
        p = provider_registry.get("local_email")
        result = asyncio.run(p.execute("email.validate", {
            "email": "test@google.com",
        }))
        assert result.status == ProviderStatus.SUCCESS
        assert result.data["domain"] == "google.com"

    def test_local_email_invalid_format(self):
        p = provider_registry.get("local_email")
        result = asyncio.run(p.execute("email.validate", {
            "email": "not-an-email",
        }))
        assert result.status == ProviderStatus.SUCCESS
        assert result.data["valid"] is False


class TestProviderCache:
    def test_cache_miss(self):
        from app.providers.cache import ProviderCache
        cache = ProviderCache()
        assert cache.get("test.cap", {"key": "val"}) is None

    def test_cache_hit(self):
        from app.providers.cache import ProviderCache
        cache = ProviderCache()
        result = ProviderResult(provider="p", capability="c", status=ProviderStatus.SUCCESS, data={"x": 1})
        cache.put("c", {"a": 1}, result, ttl=60)
        hit = cache.get("c", {"a": 1})
        assert hit is not None
        assert hit.data == {"x": 1}
        assert hit.cached is True

    def test_cache_clear(self):
        from app.providers.cache import ProviderCache
        cache = ProviderCache()
        result = ProviderResult(provider="p", capability="c", status=ProviderStatus.SUCCESS)
        cache.put("c", {"a": 1}, result)
        cache.put("c", {"a": 2}, result)
        cleared = cache.clear()
        assert cleared == 2
        assert cache.get("c", {"a": 1}) is None

    def test_cache_stats(self):
        from app.providers.cache import ProviderCache
        cache = ProviderCache()
        result = ProviderResult(provider="p", capability="c", status=ProviderStatus.SUCCESS)
        cache.put("c", {"a": 1}, result, ttl=60)
        stats = cache.stats()
        assert stats["total_entries"] == 1
        assert stats["active"] == 1


class TestCoreToolRegistration:
    def test_weather_tools_registered(self):
        from app.tools.registry import tool_registry
        assert tool_registry.is_registered("weather.current")
        assert tool_registry.is_registered("weather.forecast")

    def test_currency_tool_registered(self):
        from app.tools.registry import tool_registry
        assert tool_registry.is_registered("currency.convert")

    def test_geo_tools_registered(self):
        from app.tools.registry import tool_registry
        assert tool_registry.is_registered("geo.geocode")
        assert tool_registry.is_registered("geo.reverse_geocode")

    def test_phone_tool_registered(self):
        from app.tools.registry import tool_registry
        assert tool_registry.is_registered("phone.validate")

    def test_email_tool_registered(self):
        from app.tools.registry import tool_registry
        assert tool_registry.is_registered("email.validate")

    def test_tools_available_for_all_products(self):
        from app.tools.registry import tool_registry
        all_keys = (
            "weather.current", "weather.forecast", "currency.convert",
            "geo.geocode", "geo.reverse_geocode", "phone.validate", "email.validate",
        )
        for key in all_keys:
            tool = tool_registry.get(key)
            assert tool is not None, f"{key} not registered"
            for prod in (Product.QIAD, Product.WASLA, Product.EASY_DELIVERY, Product.ZAWED):
                assert tool.is_available_for(prod), f"{key} should be available for {prod}"
