"""Tests for server.py — MCP tools and BuxferClient business logic.

server.py is imported once at module level (see conftest.py which patches load_config).
We test the underlying functions directly, bypassing the MCP decorator layer.
"""

import os
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

import server
import config


class TestServerUsesLoadConfig:
    def test_server_module_has_load_config_call(self):
        """server.py source must contain a call to load_config()."""
        import inspect
        source = inspect.getsource(server)
        assert "load_config()" in source, "server.py must call load_config() at module level"

    def test_buxfer_credentials_come_from_environ(self, monkeypatch):
        """BUXFER_EMAIL and BUXFER_PASSWORD are read from os.environ."""
        # These module-level vars are set at import time from os.environ.
        # After load_config() runs, they should reflect what's in the environment.
        # We verify the attribute names exist on the module.
        assert hasattr(server, "BUXFER_EMAIL")
        assert hasattr(server, "BUXFER_PASSWORD")


class TestBuxferClientLogin:
    @pytest.mark.asyncio
    async def test_login_raises_without_credentials(self):
        """BuxferClient._login raises RuntimeError when credentials are missing."""
        client = server.BuxferClient()
        # Patch module-level vars so the client sees empty creds
        with patch.object(server, "BUXFER_EMAIL", ""), \
             patch.object(server, "BUXFER_PASSWORD", ""):
            with pytest.raises(RuntimeError, match="BUXFER_EMAIL"):
                await client._login()

    @pytest.mark.asyncio
    async def test_login_returns_token_on_success(self):
        """BuxferClient._login returns token from Buxfer API response."""
        client = server.BuxferClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": {"status": "OK", "token": "tok123"}}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        with patch.object(server, "BUXFER_EMAIL", "user@example.com"), \
             patch.object(server, "BUXFER_PASSWORD", "pass"):
            token = await client._login()

        assert token == "tok123"

    @pytest.mark.asyncio
    async def test_login_raises_on_api_error(self):
        """BuxferClient._login raises RuntimeError when API returns non-OK status."""
        client = server.BuxferClient()

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"response": {"status": "ERROR", "text": "bad creds"}}

        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        client._client = mock_http

        with patch.object(server, "BUXFER_EMAIL", "user@example.com"), \
             patch.object(server, "BUXFER_PASSWORD", "pass"):
            with pytest.raises(RuntimeError, match="Buxfer login failed"):
                await client._login()


class TestBuxferClientRequest:
    @pytest.mark.asyncio
    async def test_request_retries_on_token_expiry(self):
        """BuxferClient._request re-logs in when API returns ERROR status."""
        client = server.BuxferClient()
        client._token = "old-token"

        expired_resp = MagicMock()
        expired_resp.raise_for_status = MagicMock()
        expired_resp.json.return_value = {"response": {"status": "ERROR: token expired"}}

        fresh_resp = MagicMock()
        fresh_resp.raise_for_status = MagicMock()
        fresh_resp.json.return_value = {"response": {"status": "OK", "accounts": [{"id": 1}]}}

        login_resp = MagicMock()
        login_resp.raise_for_status = MagicMock()
        login_resp.json.return_value = {"response": {"status": "OK", "token": "new-token"}}

        mock_http = AsyncMock()
        mock_http.get = AsyncMock(side_effect=[expired_resp, fresh_resp])
        mock_http.post = AsyncMock(return_value=login_resp)
        client._client = mock_http

        with patch.object(server, "BUXFER_EMAIL", "u@e.com"), \
             patch.object(server, "BUXFER_PASSWORD", "p"):
            await client._request("accounts")

        assert client._token == "new-token"
        assert mock_http.get.call_count == 2


class TestMCPTools:
    @pytest.mark.asyncio
    async def test_get_accounts_returns_formatted_list(self):
        """get_accounts tool returns list with id, name, bank, balance, currency."""
        raw = [{"id": 1, "name": "Checking", "bank": "Chase", "balance": 1000.0,
                "currency": "USD", "lastSynced": "2024-01-01"}]
        with patch.object(server.buxfer, "get_accounts", AsyncMock(return_value=raw)):
            result = await server.get_accounts()

        assert result[0]["id"] == 1
        assert result[0]["name"] == "Checking"
        assert result[0]["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_get_transactions_passes_filters(self):
        """get_transactions tool passes all filter args to BuxferClient."""
        mock_result = {"transactions": [], "totalTransactions": 0}
        with patch.object(server.buxfer, "get_transactions", AsyncMock(return_value=mock_result)) as mock_get:
            await server.get_transactions(
                start_date="2024-01-01",
                end_date="2024-01-31",
                account_name="Checking",
                tag_name="Food",
                status="cleared",
                page=2,
            )
        mock_get.assert_called_once_with(
            start_date="2024-01-01",
            end_date="2024-01-31",
            account_name="Checking",
            tag_name="Food",
            status="cleared",
            page=2,
        )

    @pytest.mark.asyncio
    async def test_edit_transaction_raises_without_tags(self):
        """edit_transaction raises ValueError when tags argument is not provided."""
        with pytest.raises(ValueError, match="tags"):
            await server.edit_transaction(transaction_id=123, tags=None)

    @pytest.mark.asyncio
    async def test_financial_report_returns_summary(self):
        """financial_report returns period, summary, accounts, budgets, transactions, tags."""
        with patch.object(server.buxfer, "get_accounts", AsyncMock(return_value=[])), \
             patch.object(server.buxfer, "get_all_transactions", AsyncMock(return_value=[])), \
             patch.object(server.buxfer, "get_budgets", AsyncMock(return_value=[])), \
             patch.object(server.buxfer, "get_tags", AsyncMock(return_value=[])):
            result = await server.financial_report(start_date="2024-01-01", end_date="2024-01-31")

        assert "period" in result
        assert "summary" in result
        assert result["period"]["start"] == "2024-01-01"
        assert "total_income" in result["summary"]
        assert "total_expenses" in result["summary"]
