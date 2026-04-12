"""
Shared — Authentication Utilities.

JWT validation for API endpoints and Workload Identity helpers
for inter-service authentication.

Ref: AGENT.md Section 2, 12.
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt
from google.cloud import secretmanager

logger = logging.getLogger("fairops.shared.auth")

# JWT configuration from environment
JWT_ALGORITHM = os.environ.get("JWT_ALGORITHM", "HS256")
JWT_EXPIRE_MINUTES = int(os.environ.get("JWT_EXPIRE_MINUTES", "60"))

# Cache the JWT secret in memory after fetching from Secret Manager
_jwt_secret_cache: Optional[str] = None


def _get_jwt_secret() -> str:
    """
    Fetch JWT secret from Secret Manager.
    Cached in memory after first fetch — never re-fetched per request.
    """
    global _jwt_secret_cache
    if _jwt_secret_cache is not None:
        return _jwt_secret_cache

    # Local dev fallback
    local_secret = os.environ.get("JWT_SECRET")
    if local_secret:
        _jwt_secret_cache = local_secret
        return _jwt_secret_cache

    # Production: fetch from Secret Manager
    project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{project_id}/secrets/fairops-jwt-secret/versions/latest"

    try:
        response = client.access_secret_version(request={"name": secret_name})
        _jwt_secret_cache = response.payload.data.decode("UTF-8").strip()
        logger.info("JWT secret fetched from Secret Manager")
        return _jwt_secret_cache
    except Exception as e:
        logger.error(f"Failed to fetch JWT secret: {e}", exc_info=True)
        raise RuntimeError("Cannot start service without JWT secret") from e


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Create a JWT access token.

    Args:
        data: Claims to encode (must include "sub" for subject).
        expires_delta: Optional custom expiration. Defaults to JWT_EXPIRE_MINUTES.

    Returns:
        Encoded JWT string.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=JWT_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

    return jwt.encode(to_encode, _get_jwt_secret(), algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT string to verify.

    Returns:
        Decoded claims dictionary.

    Raises:
        JWTError: If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(
            token,
            _get_jwt_secret(),
            algorithms=[JWT_ALGORITHM],
        )
        return payload
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        raise


def extract_bearer_token(authorization: str) -> str:
    """
    Extract token from Authorization header value.

    Args:
        authorization: Header value like "Bearer eyJ..."

    Returns:
        The raw token string.

    Raises:
        ValueError: If header format is invalid.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise ValueError("Authorization header must be 'Bearer <token>'")
    return authorization[7:]


def verify_api_key(api_key: str) -> bool:
    """
    Verify an API key for the predictions ingest endpoint.

    In production, validates against Secret Manager stored keys.
    For local dev, accepts any non-empty key.

    Args:
        api_key: The X-Api-Key header value.

    Returns:
        True if valid.
    """
    if not api_key:
        return False

    # Local dev: accept any non-empty key
    if os.environ.get("ENV", "development") == "development":
        return len(api_key) > 0

    # Production: validate against stored keys
    project_id = os.environ.get("GCP_PROJECT_ID", "fairops-prod")
    client = secretmanager.SecretManagerServiceClient()
    secret_name = f"projects/{project_id}/secrets/fairops-api-keys/versions/latest"

    try:
        response = client.access_secret_version(request={"name": secret_name})
        valid_keys = response.payload.data.decode("UTF-8").strip().split(",")
        return api_key in valid_keys
    except Exception as e:
        logger.error(f"Failed to verify API key: {e}", exc_info=True)
        return False
