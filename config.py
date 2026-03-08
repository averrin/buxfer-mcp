"""Configuration loader — fetches secrets from Infisical, falls back to .env."""

import os
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

INFISICAL_DEFAULT_URL = "https://app.infisical.com"
INFISICAL_DEFAULT_PROJECT_ID = "7c539df3-0f68-42c8-91d9-b897e2a1cadf"
INFISICAL_DEFAULT_ENVIRONMENT = "prod"
INFISICAL_DEFAULT_SECRET_PATH = "/buxfer-mcp"


def load_config():
    """Load secrets from Infisical into os.environ, falling back to .env.

    Precedence (highest wins):
      1. Process environment variables (e.g. Docker ENV)
      2. Infisical secrets (if INFISICAL_CLIENT_ID/SECRET are set)
      3. .env file values
    """
    load_dotenv()

    client_id = os.environ.get("INFISICAL_CLIENT_ID")
    client_secret = os.environ.get("INFISICAL_CLIENT_SECRET")

    if not client_id or not client_secret:
        logger.info("Infisical not configured — using .env file only")
        return

    project_id = os.environ.get("INFISICAL_PROJECT_ID", INFISICAL_DEFAULT_PROJECT_ID)
    environment = os.environ.get("INFISICAL_ENVIRONMENT", INFISICAL_DEFAULT_ENVIRONMENT)
    secret_path = os.environ.get("INFISICAL_SECRET_PATH", INFISICAL_DEFAULT_SECRET_PATH)
    site_url = os.environ.get("INFISICAL_URL", INFISICAL_DEFAULT_URL).rstrip("/")

    try:
        secrets = _fetch_secrets(
            site_url, client_id, client_secret, project_id, environment, secret_path
        )
        injected = 0
        for key, value in secrets.items():
            if key not in os.environ:
                os.environ[key] = value
                injected += 1
        logger.info(
            "Loaded %d secrets from Infisical (env=%s, path=%s)",
            injected,
            environment,
            secret_path,
        )
    except Exception as e:
        logger.error("Failed to fetch secrets from Infisical: %s", e)


def _fetch_secrets(
    site_url: str,
    client_id: str,
    client_secret: str,
    project_id: str,
    environment: str,
    secret_path: str,
) -> dict[str, str]:
    """Authenticate via Universal Auth and return {key: value} map using official SDK."""
    from infisical_sdk import InfisicalSDKClient

    client = InfisicalSDKClient(host=site_url)
    client.auth.universal_auth.login(
        client_id=client_id,
        client_secret=client_secret,
    )
    response = client.secrets.list_secrets(
        environment_slug=environment,
        project_id=project_id,
        secret_path=secret_path,
    )
    return {s.secretKey: s.secretValue for s in response.secrets if s.secretKey}
