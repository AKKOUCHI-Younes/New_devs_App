import json
import unittest
from unittest.mock import AsyncMock, patch

from app.services import cache as revenue_cache


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, bytes] = {}
        self.get_calls: list[str] = []
        self.setex_calls: list[tuple[str, int, str]] = []

    async def get(self, key: str) -> bytes | None:
        self.get_calls.append(key)
        return self.values.get(key)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))
        self.values[key] = value.encode("utf-8")


def _calculated_summary(
    property_id: str,
    tenant_id: str,
    month: int | None = None,
    year: int | None = None,
    currency: str | None = None,
) -> dict[str, object]:
    del month, year
    totals = {
        ("tenant-a", "prop-001"): ("2250.00", 4),
        ("tenant-b", "prop-001"): ("0.00", 0),
    }
    total, count = totals[(tenant_id, property_id)]
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": total,
        "currency": currency or "USD",
        "count": count,
    }


class RevenueCacheIsolationTests(unittest.IsolatedAsyncioTestCase):
    async def _exercise_access_order(self, tenants: tuple[str, str]) -> None:
        fake_redis = FakeRedis()
        calculator = AsyncMock(side_effect=_calculated_summary)

        with (
            patch.object(revenue_cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_total_revenue", calculator),
        ):
            results = []
            for tenant_id in tenants:
                results.append(
                    await revenue_cache.get_revenue_summary(
                        "prop-001",
                        tenant_id,
                        month=3,
                        year=2024,
                        currency="USD",
                    )
                )

            expected_totals = {
                "tenant-a": ("2250.00", 4),
                "tenant-b": ("0.00", 0),
            }
            for tenant_id, result in zip(tenants, results):
                self.assertEqual(
                    (result["total"], result["count"]),
                    expected_totals[tenant_id],
                )
                self.assertEqual(result["tenant_id"], tenant_id)

            self.assertEqual(calculator.await_count, 2)
            self.assertEqual(len(fake_redis.values), 2)

            keys = tuple(fake_redis.values)
            for tenant_id in tenants:
                tenant_keys = [key for key in keys if tenant_id in key]
                self.assertEqual(len(tenant_keys), 1)
                key = tenant_keys[0]
                self.assertIn("prop-001", key)
                self.assertIn("2024", key)
                self.assertIn("USD", key)

            first_tenant = tenants[0]
            cached = await revenue_cache.get_revenue_summary(
                "prop-001",
                first_tenant,
                month=3,
                year=2024,
                currency="USD",
            )
            self.assertEqual(cached["tenant_id"], first_tenant)
            self.assertEqual(calculator.await_count, 2)

            for key, ttl, payload in fake_redis.setex_calls:
                self.assertGreater(ttl, 0)
                self.assertEqual(json.loads(payload)["tenant_id"], next(
                    tenant_id for tenant_id in tenants if tenant_id in key
                ))

    async def test_cache_is_isolated_when_sunset_warms_first(self) -> None:
        await self._exercise_access_order(("tenant-a", "tenant-b"))

    async def test_cache_is_isolated_when_ocean_warms_first(self) -> None:
        await self._exercise_access_order(("tenant-b", "tenant-a"))

    async def test_period_and_currency_are_cache_key_dimensions(self) -> None:
        fake_redis = FakeRedis()
        calculator = AsyncMock(side_effect=_calculated_summary)
        dimensions = (
            (3, 2024, "USD"),
            (4, 2024, "USD"),
            (3, 2025, "USD"),
            (3, 2024, "EUR"),
        )

        with (
            patch.object(revenue_cache, "redis_client", fake_redis),
            patch("app.services.reservations.calculate_total_revenue", calculator),
        ):
            for month, year, currency in dimensions:
                await revenue_cache.get_revenue_summary(
                    "prop-001",
                    "tenant-a",
                    month=month,
                    year=year,
                    currency=currency,
                )

            self.assertEqual(calculator.await_count, len(dimensions))
            self.assertEqual(len(fake_redis.values), len(dimensions))

            await revenue_cache.get_revenue_summary(
                "prop-001",
                "tenant-a",
                month=3,
                year=2024,
                currency="USD",
            )
            self.assertEqual(calculator.await_count, len(dimensions))


if __name__ == "__main__":
    unittest.main()
