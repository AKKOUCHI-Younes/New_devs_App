# Property Revenue Dashboard

This repository contains a React/Vite dashboard backed by FastAPI, PostgreSQL,
and Redis. The revenue path is tenant-scoped and supports property-local monthly
reporting with exact decimal aggregation.

## Run locally

Docker is the supported development path:

```bash
docker compose up --build
```

- Dashboard: <http://localhost:3000>
- API documentation: <http://localhost:8000/docs>
- PostgreSQL: `localhost:5433`
- Redis: `localhost:6380`

The database schema and challenge fixtures are loaded automatically from
`database/schema.sql` and `database/seed.sql`.

## Verify

Run all backend unit and seeded-database integration tests:

```bash
docker compose exec -T -e RUN_DB_INTEGRATION=1 backend python -m unittest discover -s tests -v
```

Build the production frontend:

```bash
docker compose build frontend
```

The focused backend suite covers tenant authorization, cache isolation in both
access orders, property ownership, timezone boundaries, currency handling, and
decimal rounding. The dashboard retrieves its property list from the
authenticated tenant and sends an explicit reporting month to the API.

## Revenue API behavior

- `GET /api/v1/dashboard/properties` lists only the authenticated tenant's properties.
- `GET /api/v1/dashboard/summary?property_id=...&year=...&month=...` reports one property-local calendar month.
- Tenant identity is taken from verified server-side authentication context.
- Cache entries include tenant, property, period, and currency.
- Monetary values are summed as PostgreSQL `NUMERIC`/Python `Decimal` and rounded once with `ROUND_HALF_UP`.
- Database failures return a service error; the API never substitutes fabricated revenue.
