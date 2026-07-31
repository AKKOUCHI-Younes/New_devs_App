import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.services.cache import get_revenue_summary
from app.core.auth import authenticate_request as get_current_user
from app.services.reservations import (
    MixedCurrenciesError,
    PropertyNotFoundError,
    get_tenant_properties,
)


logger = logging.getLogger(__name__)

router = APIRouter()

@router.get("/dashboard/summary")
async def get_dashboard_summary(
    property_id: str,
    month: Optional[int] = Query(default=None, ge=1, le=12),
    year: Optional[int] = Query(default=None, ge=1, le=9999),
    currency: Optional[str] = Query(default=None, min_length=3, max_length=3, pattern="^[A-Za-z]{3}$"),
    current_user: dict = Depends(get_current_user),
) -> Dict[str, Any]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context is required")
    if (month is None) != (year is None):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="month and year must be provided together")

    try:
        revenue_data = await get_revenue_summary(
            property_id,
            tenant_id,
            month=month,
            year=year,
            currency=currency,
        )
    except PropertyNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Property not found")
    except MixedCurrenciesError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    except HTTPException:
        raise
    except Exception:
        logger.exception("Revenue summary calculation failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Revenue data is temporarily unavailable")

    return {
        "property_id": revenue_data["property_id"],
        # Arithmetic and rounding stay Decimal until this contract-preserving JSON boundary.
        "total_revenue": float(revenue_data["total"]),
        "currency": revenue_data["currency"],
        "reservations_count": revenue_data["count"],
        "period": revenue_data.get("period"),
    }


@router.get("/dashboard/properties")
async def get_dashboard_properties(
    current_user: dict = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant context is required")

    try:
        return await get_tenant_properties(tenant_id)
    except Exception:
        logger.exception("Tenant property lookup failed")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Property data is temporarily unavailable")
