from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from jose import jwt

from app.config import settings
from app.core import auth
from app.core.tenant_resolver import TenantResolver


class FakeResponse:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data


class FakeQuery:
    def __init__(self, data: list[dict[str, object]]) -> None:
        self.data = data

    def select(self, *args: object, **kwargs: object) -> "FakeQuery":
        del args, kwargs
        return self

    def eq(self, *args: object, **kwargs: object) -> "FakeQuery":
        del args, kwargs
        return self

    def in_(self, *args: object, **kwargs: object) -> "FakeQuery":
        del args, kwargs
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self.data)


class FakeService:
    def __init__(self, memberships: list[dict[str, object]]) -> None:
        self.memberships = memberships

    def table(self, name: str) -> FakeQuery:
        rows_by_table = {
            "user_permissions": [],
            "users_city": [],
            "user_tenants": self.memberships,
            "all_properties": [],
        }
        return FakeQuery(rows_by_table[name])


def make_token(
    *,
    app_tenant: str | None,
    user_tenant: str | None = None,
) -> str:
    app_metadata = {"role": "user"}
    if app_tenant is not None:
        app_metadata["tenant_id"] = app_tenant

    user_metadata: dict[str, str] = {"name": "Tenant Test User"}
    if user_tenant is not None:
        user_metadata["tenant_id"] = user_tenant

    payload = {
        "id": "tenant-test-user",
        "email": "tenant-test@example.com",
        "app_metadata": app_metadata,
        "user_metadata": user_metadata,
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, settings.secret_key, algorithm="HS256")


class AuthenticatedTenantSelectionTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        auth.clear_auth_cache()

    async def authenticate(
        self,
        *,
        app_tenant: str | None,
        user_tenant: str | None,
        memberships: list[dict[str, object]],
    ):
        token = make_token(app_tenant=app_tenant, user_tenant=user_tenant)
        fake_supabase = SimpleNamespace(service=FakeService(memberships))

        with patch.object(auth, "supabase", fake_supabase):
            return await auth.authenticate_request(
                credentials=SimpleNamespace(credentials=token)
            )

    async def test_server_app_metadata_wins_over_spoofed_user_metadata(self) -> None:
        user = await self.authenticate(
            app_tenant="tenant-a",
            user_tenant="tenant-b",
            memberships=[{"tenant_id": "tenant-a", "role": "user"}],
        )

        self.assertEqual(user.tenant_id, "tenant-a")

    async def test_app_metadata_must_match_an_active_membership(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await self.authenticate(
                app_tenant="tenant-b",
                user_tenant=None,
                memberships=[{"tenant_id": "tenant-a", "role": "user"}],
            )

        self.assertEqual(raised.exception.status_code, 403)

    async def test_resolver_never_maps_an_email_to_a_default_tenant(self) -> None:
        tenant_id = await TenantResolver.resolve_tenant_id(
            user_id="unknown-user",
            user_email="sunset@propertyflow.com",
        )

        self.assertIsNone(tenant_id)

    async def test_resolver_ignores_user_editable_metadata_claim(self) -> None:
        token = make_token(app_tenant=None, user_tenant="tenant-b")

        tenant_id = await TenantResolver.resolve_tenant_id(
            user_id="tenant-test-user",
            user_email="tenant-test@example.com",
            token=token,
        )

        self.assertIsNone(tenant_id)

    async def test_matching_app_metadata_and_active_membership_is_accepted(self) -> None:
        user = await self.authenticate(
            app_tenant="tenant-b",
            user_tenant=None,
            memberships=[{"tenant_id": "tenant-b", "role": "user"}],
        )

        self.assertEqual(user.tenant_id, "tenant-b")

    async def test_single_active_membership_is_the_safe_fallback(self) -> None:
        user = await self.authenticate(
            app_tenant=None,
            user_tenant="tenant-b",
            memberships=[{"tenant_id": "tenant-a", "role": "user"}],
        )

        self.assertEqual(user.tenant_id, "tenant-a")

    async def test_ambiguous_memberships_without_server_selection_are_rejected(self) -> None:
        with self.assertRaises(HTTPException) as raised:
            await self.authenticate(
                app_tenant=None,
                user_tenant="tenant-b",
                memberships=[
                    {"tenant_id": "tenant-a", "role": "user"},
                    {"tenant_id": "tenant-b", "role": "user"},
                ],
            )

        self.assertEqual(raised.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
