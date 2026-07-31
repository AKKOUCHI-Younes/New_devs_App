import json
import logging
import redis.asyncio as redis
from typing import Dict, Any, Optional
import os
from urllib.parse import quote


logger = logging.getLogger(__name__)

# Initialize Redis client (typically configured centrally).
redis_client = redis.Redis.from_url(
    os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    socket_connect_timeout=1.0,
    socket_timeout=1.0,
)

def revenue_cache_key(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    currency: Optional[str] = None,
) -> str:
    """Build a cache key containing every request dimension that affects revenue."""
    period = f"{year:04d}-{month:02d}" if month is not None and year is not None else "all"
    currency_key = currency.upper() if currency else "all"
    dimensions = (tenant_id, property_id, period, currency_key)
    return "revenue:" + ":".join(quote(str(value), safe="") for value in dimensions)


async def get_revenue_summary(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
    currency: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fetches revenue summary, utilizing caching to improve performance.
    """
    cache_key = revenue_cache_key(property_id, tenant_id, month, year, currency)
    
    # Try to get from cache
    try:
        cached = await redis_client.get(cache_key)
        if cached:
            cached_summary = json.loads(cached)
            required_fields = {"property_id", "tenant_id", "total", "currency", "count"}
            if (
                not isinstance(cached_summary, dict)
                or not required_fields.issubset(cached_summary)
                or cached_summary["property_id"] != property_id
                or cached_summary["tenant_id"] != tenant_id
            ):
                raise ValueError("cached revenue payload does not match its scope")
            return cached_summary
    except (redis.RedisError, json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError) as exc:
        # Revenue remains available if the optional cache is temporarily down.
        logger.warning("Revenue cache read ignored: %s", type(exc).__name__)
    
    # Revenue calculation is delegated to the reservation service.
    from app.services.reservations import calculate_total_revenue
    
    # Calculate revenue
    result = await calculate_total_revenue(
        property_id,
        tenant_id,
        month=month,
        year=year,
        currency=currency,
    )
    
    # Cache the result for 5 minutes
    try:
        await redis_client.setex(cache_key, 300, json.dumps(result))
    except redis.RedisError as exc:
        logger.warning("Revenue cache write failed: %s", type(exc).__name__)
    
    return result
