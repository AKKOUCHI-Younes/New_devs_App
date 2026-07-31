from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1 import dashboard


class DashboardRevenueTests(unittest.IsolatedAsyncioTestCase):
    async def test_forwards_authenticated_tenant_and_optional_period(self) -> None:
        summary = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "total": "2250.00",
            "currency": "USD",
            "count": 4,
            "period": {"month": 3, "year": 2024},
        }
        calculator = AsyncMock(return_value=summary)
        current_user = SimpleNamespace(tenant_id="tenant-a")

        with patch.object(dashboard, "get_revenue_summary", calculator):
            response = await dashboard.get_dashboard_summary(
                property_id="prop-001",
                month=3,
                year=2024,
                currency="USD",
                current_user=current_user,
            )

        calculator.assert_awaited_once_with(
            "prop-001",
            "tenant-a",
            month=3,
            year=2024,
            currency="USD",
        )
        self.assertEqual(response["total_revenue"], 2250.0)
        self.assertEqual(response["reservations_count"], 4)

    async def test_rejects_an_incomplete_month_year_pair(self) -> None:
        current_user = SimpleNamespace(tenant_id="tenant-a")

        with self.assertRaises(HTTPException) as raised:
            await dashboard.get_dashboard_summary(
                property_id="prop-001",
                month=3,
                year=None,
                currency="USD",
                current_user=current_user,
            )

        self.assertEqual(raised.exception.status_code, 422)

    async def test_requires_server_side_tenant_context(self) -> None:
        calculator = AsyncMock()
        current_user = SimpleNamespace(tenant_id=None)

        with (
            patch.object(dashboard, "get_revenue_summary", calculator),
            self.assertRaises(HTTPException) as raised,
        ):
            await dashboard.get_dashboard_summary(
                property_id="prop-001",
                month=3,
                year=2024,
                currency="USD",
                current_user=current_user,
            )

        self.assertEqual(raised.exception.status_code, 403)
        calculator.assert_not_awaited()

    async def test_invalid_reporting_boundary_is_a_validation_error(self) -> None:
        calculator = AsyncMock(side_effect=ValueError("year must be between 2 and 9998"))
        current_user = SimpleNamespace(tenant_id="tenant-a")

        with (
            patch.object(dashboard, "get_revenue_summary", calculator),
            self.assertRaises(HTTPException) as raised,
        ):
            await dashboard.get_dashboard_summary(
                property_id="prop-001",
                month=12,
                year=9999,
                currency="USD",
                current_user=current_user,
            )

        self.assertEqual(raised.exception.status_code, 422)


if __name__ == "__main__":
    unittest.main()
