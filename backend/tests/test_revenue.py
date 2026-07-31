from datetime import datetime, timezone
from decimal import Decimal
import unittest

from app.services.reservations import monthly_utc_bounds, round_money


UTC = timezone.utc


class MonthlyUtcBoundsTests(unittest.TestCase):
    def test_paris_march_uses_local_calendar_boundaries(self) -> None:
        start, end = monthly_utc_bounds(2024, 3, "Europe/Paris")

        self.assertEqual(start, datetime(2024, 2, 29, 23, 0, tzinfo=UTC))
        self.assertEqual(end, datetime(2024, 3, 31, 22, 0, tzinfo=UTC))

        seeded_check_in = datetime(2024, 2, 29, 23, 30, tzinfo=UTC)
        self.assertLessEqual(start, seeded_check_in)
        self.assertLess(seeded_check_in, end)

    def test_new_york_march_accounts_for_dst(self) -> None:
        start, end = monthly_utc_bounds(2024, 3, "America/New_York")

        self.assertEqual(start, datetime(2024, 3, 1, 5, 0, tzinfo=UTC))
        self.assertEqual(end, datetime(2024, 4, 1, 4, 0, tzinfo=UTC))

    def test_bounds_are_half_open(self) -> None:
        start, end = monthly_utc_bounds(2024, 3, "Europe/Paris")

        self.assertTrue(start <= start < end)
        self.assertFalse(start <= end < end)

    def test_december_rolls_over_to_the_next_year(self) -> None:
        start, end = monthly_utc_bounds(2024, 12, "Europe/Paris")

        self.assertEqual(start, datetime(2024, 11, 30, 23, 0, tzinfo=UTC))
        self.assertEqual(end, datetime(2024, 12, 31, 23, 0, tzinfo=UTC))


class MoneyRoundingTests(unittest.TestCase):
    def test_rounds_half_up_at_a_positive_half_cent(self) -> None:
        self.assertEqual(str(round_money(Decimal("1.005"))), "1.01")

    def test_rounds_half_up_away_from_zero_for_negative_money(self) -> None:
        self.assertEqual(str(round_money(Decimal("-1.005"))), "-1.01")

    def test_aggregates_sub_cent_amounts_before_rounding(self) -> None:
        amounts = (Decimal("333.333"), Decimal("333.333"), Decimal("333.334"))

        self.assertEqual(sum(amounts, Decimal("0")), Decimal("1000.000"))
        self.assertEqual(str(round_money(sum(amounts, Decimal("0")))), "1000.00")


if __name__ == "__main__":
    unittest.main()
