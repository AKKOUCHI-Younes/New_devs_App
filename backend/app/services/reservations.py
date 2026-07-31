from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database_pool import db_pool


CENT = Decimal("0.01")


class PropertyNotFoundError(LookupError):
    """Raised when a property does not belong to the authenticated tenant."""

    def __init__(self, property_id: str) -> None:
        self.property_id = property_id
        super().__init__(f"Property {property_id!r} was not found")


class MixedCurrenciesError(ValueError):
    """Raised when one total would combine monetary values in different currencies."""

    def __init__(self, currencies: List[Optional[str]]) -> None:
        self.currencies = currencies
        labels = ", ".join(sorted(currency or "unspecified" for currency in currencies))
        super().__init__(f"A currency must be selected; reservations use: {labels}")


def round_money(value: Any) -> Decimal:
    """Round an aggregate monetary value to cents using the finance rule."""
    if value is None:
        decimal_value = Decimal("0")
    elif isinstance(value, Decimal):
        decimal_value = value
    else:
        decimal_value = Decimal(str(value))
    return decimal_value.quantize(CENT, rounding=ROUND_HALF_UP)


def monthly_utc_bounds(year: int, month: int, timezone_name: str) -> Tuple[datetime, datetime]:
    """Return half-open UTC bounds for a calendar month in a property's timezone."""
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")

    property_timezone = ZoneInfo(timezone_name)
    local_start = datetime(year, month, 1, tzinfo=property_timezone)
    if month == 12:
        local_end = datetime(year + 1, 1, 1, tzinfo=property_timezone)
    else:
        local_end = datetime(year, month + 1, 1, tzinfo=property_timezone)

    return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)


def _validate_period(month: Optional[int], year: Optional[int]) -> Optional[str]:
    if (month is None) != (year is None):
        raise ValueError("month and year must be provided together")
    if month is None or year is None:
        return None
    if not 1 <= month <= 12:
        raise ValueError("month must be between 1 and 12")
    # Constructing the date also validates the supported year range.
    datetime(year, month, 1)
    return f"{year:04d}-{month:02d}"


def _normalize_currency(currency: Optional[str]) -> Optional[str]:
    if currency is None:
        return None
    normalized = currency.strip().upper()
    if not normalized:
        raise ValueError("currency must not be blank")
    return normalized


async def _property_for_tenant(
    session: AsyncSession,
    property_id: str,
    tenant_id: str,
) -> Dict[str, Any]:
    result = await session.execute(
        text(
            """
            SELECT id, name, timezone
            FROM properties
            WHERE id = :property_id AND tenant_id = :tenant_id
            """
        ),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    property_row = result.mappings().first()
    if property_row is None:
        raise PropertyNotFoundError(property_id)
    return dict(property_row)


async def _calculate_revenue(
    session: AsyncSession,
    property_id: str,
    tenant_id: str,
    month: Optional[int],
    year: Optional[int],
    currency: Optional[str],
) -> Dict[str, Any]:
    if not property_id or not tenant_id:
        raise ValueError("property_id and tenant_id are required")

    period = _validate_period(month, year)
    selected_currency = _normalize_currency(currency)
    property_row = await _property_for_tenant(session, property_id, tenant_id)

    clauses = [
        "r.property_id = :property_id",
        "r.tenant_id = :tenant_id",
    ]
    parameters: Dict[str, Any] = {
        "property_id": property_id,
        "tenant_id": tenant_id,
    }

    if period is not None:
        start_at, end_at = monthly_utc_bounds(
            year=year,  # type: ignore[arg-type]
            month=month,  # type: ignore[arg-type]
            timezone_name=property_row["timezone"],
        )
        clauses.extend(
            [
                "r.check_in_date >= :start_at",
                "r.check_in_date < :end_at",
            ]
        )
        parameters.update({"start_at": start_at, "end_at": end_at})

    if selected_currency is not None:
        clauses.append("UPPER(r.currency) = :currency")
        parameters["currency"] = selected_currency

    result = await session.execute(
        text(
            f"""
            SELECT UPPER(r.currency) AS currency,
                   SUM(r.total_amount) AS total_revenue,
                   COUNT(*) AS reservation_count
            FROM reservations AS r
            WHERE {' AND '.join(clauses)}
            GROUP BY UPPER(r.currency)
            ORDER BY UPPER(r.currency)
            """
        ),
        parameters,
    )
    rows = [dict(row) for row in result.mappings().all()]

    if selected_currency is None and len(rows) > 1:
        raise MixedCurrenciesError([row["currency"] for row in rows])

    if rows:
        row = rows[0]
        total = round_money(row["total_revenue"])
        reservation_count = int(row["reservation_count"])
        resolved_currency = row["currency"]
    else:
        total = round_money(Decimal("0"))
        reservation_count = 0
        # With no reservations there is no row to infer from; preserve the
        # schema's documented default rather than returning an invalid null.
        resolved_currency = selected_currency or "USD"

    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": format(total, ".2f"),
        "currency": resolved_currency,
        "count": reservation_count,
        "period": period or "all",
    }


async def calculate_total_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """Calculate exact tenant-scoped revenue, optionally for one local calendar month."""
    await db_pool.initialize()
    async with db_pool.get_session() as session:
        return await _calculate_revenue(
            session=session,
            property_id=property_id,
            tenant_id=tenant_id,
            month=month,
            year=year,
            currency=currency,
        )


async def calculate_monthly_revenue(
    property_id: str,
    month: int,
    year: int,
    tenant_id: str,
    db_session: Optional[AsyncSession] = None,
    currency: Optional[str] = None,
) -> Decimal:
    """Backward-compatible monthly helper that now requires an explicit tenant."""
    if db_session is not None:
        result = await _calculate_revenue(
            session=db_session,
            property_id=property_id,
            tenant_id=tenant_id,
            month=month,
            year=year,
            currency=currency,
        )
    else:
        result = await calculate_total_revenue(
            property_id=property_id,
            tenant_id=tenant_id,
            month=month,
            year=year,
            currency=currency,
        )
    return Decimal(result["total"])


async def get_tenant_properties(tenant_id: str) -> List[Dict[str, Any]]:
    """List only a tenant's properties and their latest local reporting month."""
    if not tenant_id:
        raise ValueError("tenant_id is required")

    await db_pool.initialize()
    async with db_pool.get_session() as session:
        result = await session.execute(
            text(
                """
                SELECT p.id,
                       p.name,
                       p.timezone,
                       MAX(r.check_in_date) AS latest_check_in
                FROM properties AS p
                LEFT JOIN reservations AS r
                  ON r.property_id = p.id
                 AND r.tenant_id = p.tenant_id
                WHERE p.tenant_id = :tenant_id
                GROUP BY p.id, p.name, p.timezone
                ORDER BY p.name, p.id
                """
            ),
            {"tenant_id": tenant_id},
        )

        properties: List[Dict[str, Any]] = []
        for row_mapping in result.mappings().all():
            row = dict(row_mapping)
            latest_check_in = row.pop("latest_check_in")
            if latest_check_in is None:
                latest_period = None
            else:
                if latest_check_in.tzinfo is None:
                    latest_check_in = latest_check_in.replace(tzinfo=timezone.utc)
                latest_period = latest_check_in.astimezone(
                    ZoneInfo(row["timezone"])
                ).strftime("%Y-%m")
            row["latest_period"] = latest_period
            properties.append(row)

        return properties
