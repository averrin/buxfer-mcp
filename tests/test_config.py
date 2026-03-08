"""Tests for config.py — Infisical integration and .env fallback."""

import os
import importlib
import sys
from unittest.mock import MagicMock, patch


def _reload_config():
    """Force re-import of config so load_config() re-runs with fresh env."""
    if "config" in sys.modules:
        del sys.modules["config"]
    import config
    return config


class TestLoadConfig:
    def test_no_infisical_creds_uses_dotenv_only(self, tmp_path, monkeypatch):
        """When INFISICAL_CLIENT_ID/SECRET are absent, only .env is loaded."""
        monkeypatch.delenv("INFISICAL_CLIENT_ID", raising=False)
        monkeypatch.delenv("INFISICAL_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("BUXFER_EMAIL", raising=False)
        monkeypatch.delenv("BUXFER_PASSWORD", raising=False)

        config = _reload_config()
        with patch("config.load_dotenv", lambda: os.environ.update({"BUXFER_EMAIL": "test@example.com", "BUXFER_PASSWORD": "secret"})):
            config.load_config()

        assert os.environ.get("BUXFER_EMAIL") == "test@example.com"
        assert os.environ.get("BUXFER_PASSWORD") == "secret"

    def test_infisical_secrets_injected_into_environ(self, tmp_path, monkeypatch):
        """When Infisical creds are set, secrets are fetched and injected."""
        monkeypatch.setenv("INFISICAL_CLIENT_ID", "client-id")
        monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")
        monkeypatch.delenv("BUXFER_EMAIL", raising=False)
        monkeypatch.delenv("BUXFER_PASSWORD", raising=False)

        config = _reload_config()
        with patch("config.load_dotenv"), \
             patch.object(config, "_fetch_secrets", return_value={"BUXFER_EMAIL": "infisical@example.com"}):
            config.load_config()

        assert os.environ.get("BUXFER_EMAIL") == "infisical@example.com"

    def test_process_env_not_overwritten_by_infisical(self, tmp_path, monkeypatch):
        """Process env vars take precedence over Infisical secrets."""
        monkeypatch.setenv("INFISICAL_CLIENT_ID", "client-id")
        monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")
        monkeypatch.setenv("BUXFER_EMAIL", "process@example.com")

        config = _reload_config()
        with patch("config.load_dotenv"), \
             patch.object(config, "_fetch_secrets", return_value={"BUXFER_EMAIL": "infisical@example.com"}):
            config.load_config()

        assert os.environ.get("BUXFER_EMAIL") == "process@example.com"

    def test_infisical_error_is_non_fatal(self, monkeypatch):
        """Infisical fetch failure does not raise — falls back gracefully."""
        monkeypatch.setenv("INFISICAL_CLIENT_ID", "client-id")
        monkeypatch.setenv("INFISICAL_CLIENT_SECRET", "client-secret")
        monkeypatch.delenv("BUXFER_EMAIL", raising=False)

        config = _reload_config()
        with patch("config.load_dotenv", lambda: os.environ.update({"BUXFER_EMAIL": "fallback@example.com"})), \
             patch.object(config, "_fetch_secrets", side_effect=RuntimeError("connection refused")):
            config.load_config()  # must not raise

        assert os.environ.get("BUXFER_EMAIL") == "fallback@example.com"

    def test_default_infisical_project_id_is_set(self):
        """Default INFISICAL_PROJECT_ID constant is defined in config."""
        config = _reload_config()
        assert hasattr(config, "INFISICAL_DEFAULT_PROJECT_ID")
        assert config.INFISICAL_DEFAULT_PROJECT_ID  # non-empty

    def test_default_secret_path_is_buxfer_mcp(self):
        """Default secret path is /buxfer-mcp."""
        config = _reload_config()
        assert config.INFISICAL_DEFAULT_SECRET_PATH == "/buxfer-mcp"


class TestFetchSecrets:
    def test_fetch_secrets_calls_sdk_correctly(self, monkeypatch):
        """_fetch_secrets authenticates with Universal Auth and lists secrets."""
        mock_client = MagicMock()
        mock_secret = MagicMock()
        mock_secret.secretKey = "MY_SECRET"
        mock_secret.secretValue = "my_value"
        mock_client.secrets.list_secrets.return_value.secrets = [mock_secret]

        mock_sdk_cls = MagicMock(return_value=mock_client)

        config = _reload_config()
        with patch.dict("sys.modules", {"infisical_sdk": MagicMock(InfisicalSDKClient=mock_sdk_cls)}):
            result = config._fetch_secrets(
                site_url="https://app.infisical.com",
                client_id="cid",
                client_secret="csecret",
                project_id="proj-uuid",
                environment="prod",
                secret_path="/buxfer-mcp",
            )

        mock_sdk_cls.assert_called_once_with(host="https://app.infisical.com")
        mock_client.auth.universal_auth.login.assert_called_once_with(
            client_id="cid", client_secret="csecret"
        )
        mock_client.secrets.list_secrets.assert_called_once_with(
            environment_slug="prod",
            project_id="proj-uuid",
            secret_path="/buxfer-mcp",
        )
        assert result == {"MY_SECRET": "my_value"}

    def test_fetch_secrets_skips_empty_keys(self, monkeypatch):
        """Secrets with empty secretKey are excluded from result."""
        mock_client = MagicMock()
        good = MagicMock()
        good.secretKey = "VALID_KEY"
        good.secretValue = "value"
        bad = MagicMock()
        bad.secretKey = ""
        bad.secretValue = "should-be-skipped"
        mock_client.secrets.list_secrets.return_value.secrets = [good, bad]

        mock_sdk_cls = MagicMock(return_value=mock_client)

        config = _reload_config()
        with patch.dict("sys.modules", {"infisical_sdk": MagicMock(InfisicalSDKClient=mock_sdk_cls)}):
            result = config._fetch_secrets(
                "https://app.infisical.com", "cid", "cs", "proj", "prod", "/"
            )

        assert "VALID_KEY" in result
        assert "" not in result
