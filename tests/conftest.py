"""Shared pytest fixtures for buxfer-mcp tests."""

import sys
from unittest.mock import patch

# Patch load_dotenv and _fetch_secrets before server.py is imported,
# so tests don't need real credentials or Infisical access.
_load_dotenv_patcher = patch("dotenv.load_dotenv")
_load_dotenv_patcher.start()


def pytest_sessionfinish(session, exitstatus):
    _load_dotenv_patcher.stop()
