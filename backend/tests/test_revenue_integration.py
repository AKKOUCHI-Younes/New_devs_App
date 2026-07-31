import os
import unittest

from app.core.database_pool import db_pool
from app.services.reservations import calculate_total_revenue


RUN_DB_INTEGRATION = os.getenv("RUN_DB_INTEGRATION") == "1"


@unittest.skipUnless(
    RUN_DB_INTEGRATION,
    "set RUN_DB_INTEGRATION=1 when the seeded PostgreSQL service is available",
)
class SeededRevenueIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncTearDown(self) -> None:
        # IsolatedAsyncioTestCase uses a fresh event loop for each method, while
        # asyncpg pool connections are tied to the loop that created them.
        await db_pool.close()

    async def test_shared_property_id_is_tenant_scoped(self) -> None:
        sunset = await calculate_total_revenue(
            "prop-001",
            "tenant-a",
            month=3,
            year=2024,
            currency="USD",
        )
        ocean = await calculate_total_revenue(
            "prop-001",
            "tenant-b",
            month=3,
            year=2024,
            currency="USD",
        )

        self.assertEqual((sunset["total"], sunset["count"]), ("2250.00", 4))
        self.assertEqual((ocean["total"], ocean["count"]), ("0.00", 0))
        self.assertEqual(sunset["tenant_id"], "tenant-a")
        self.assertEqual(ocean["tenant_id"], "tenant-b")

    async def test_seeded_totals_for_each_clients_properties(self) -> None:
        expected = {
            ("tenant-a", "prop-002"): ("4975.50", 4),
            ("tenant-a", "prop-003"): ("6100.50", 2),
            ("tenant-b", "prop-004"): ("1776.50", 4),
            ("tenant-b", "prop-005"): ("3256.00", 3),
        }

        for (tenant_id, property_id), expected_summary in expected.items():
            with self.subTest(tenant_id=tenant_id, property_id=property_id):
                result = await calculate_total_revenue(
                    property_id,
                    tenant_id,
                    month=3,
                    year=2024,
                    currency="USD",
                )
                self.assertEqual(
                    (result["total"], result["count"]),
                    expected_summary,
                )


if __name__ == "__main__":
    unittest.main()
