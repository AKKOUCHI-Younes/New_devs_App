"""
Minimal tenant resolver for authentication.
"""
from typing import Optional
import logging

from jose import JWTError, jwt

from ..config import settings

logger = logging.getLogger(__name__)


class TenantResolver:
    """Minimal tenant resolver that extracts tenant_id from JWT claims."""

    @staticmethod
    def resolve_tenant_from_token(token_payload: dict) -> Optional[str]:
        """
        Extract tenant_id from JWT token payload.

        Args:
            token_payload: Decoded JWT payload

        Returns:
            Tenant ID if found, None otherwise
        """
        # app_metadata is controlled by the identity provider; user_metadata is
        # deliberately ignored because users can edit it themselves.
        if 'app_metadata' in token_payload:
            tenant_id = token_payload['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        # Try root level
        tenant_id = token_payload.get('tenant_id')
        if tenant_id:
            return tenant_id

        logger.warning("No tenant_id found in token payload")
        return None

    @staticmethod
    def resolve_tenant_from_user(user_data: dict) -> Optional[str]:
        """
        Extract tenant_id from user data.

        Args:
            user_data: User data dictionary

        Returns:
            Tenant ID if found, None otherwise
        """
        # Prefer identity-provider-controlled metadata and deliberately ignore
        # user-editable user_metadata for authorization.
        if 'app_metadata' in user_data:
            tenant_id = user_data['app_metadata'].get('tenant_id')
            if tenant_id:
                return tenant_id

        if 'tenant_id' in user_data:
            return user_data['tenant_id']

        return None

    @staticmethod
    async def resolve_tenant_id(
        user_id: str,
        user_email: str,
        token: Optional[str] = None,
    ) -> Optional[str]:
        """
        Resolve tenant ID for a user.
        
        Args:
            user_id: User ID
            user_email: User email
            
        Returns:
            Tenant ID
        """
        del user_id
        if token:
            try:
                payload = jwt.decode(
                    token,
                    settings.secret_key,
                    algorithms=["HS256"],
                    audience="authenticated",
                )
                return TenantResolver.resolve_tenant_from_token(payload)
            except JWTError:
                logger.warning("Could not resolve tenant from verified token claims")

        # An email address is identity data, not authorization. Callers without
        # a verified claim or server-side membership must fail closed.
        logger.warning("No trusted tenant context for authenticated user %s", user_email)
        return None

    @staticmethod
    async def update_user_tenant_metadata(user_id: str, tenant_id: str) -> None:
        """
        Update user metadata with tenant_id.
        
        Args:
            user_id: User ID
            tenant_id: Tenant ID
        """
        # No-op in this resolver implementation.
        pass
