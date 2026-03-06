import os
import httpx
from dotenv import load_dotenv
from datetime import datetime, timedelta
from mcp.server.fastmcp import FastMCP

load_dotenv()

# --- Configuration ---
BUXFER_EMAIL = os.environ.get("BUXFER_EMAIL", "")
BUXFER_PASSWORD = os.environ.get("BUXFER_PASSWORD", "")
BASE_URL = "https://www.buxfer.com/api"

mcp = FastMCP("Buxfer")

# --- Buxfer API Client ---

class BuxferClient:
    """Thin async client for the Buxfer REST API."""

    def __init__(self):
        self._token: str | None = None
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def _login(self) -> str:
        if not BUXFER_EMAIL or not BUXFER_PASSWORD:
            raise RuntimeError(
                "BUXFER_EMAIL and BUXFER_PASSWORD environment variables must be set"
            )
        client = await self._ensure_client()
        resp = await client.post(
            f"{BASE_URL}/login",
            data={"userid": BUXFER_EMAIL, "password": BUXFER_PASSWORD},
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("response", {}).get("status")
        if status != "OK":
            raise RuntimeError(f"Buxfer login failed: {data}")
        self._token = data["response"]["token"]
        return self._token

    async def _get_token(self) -> str:
        if self._token is None:
            return await self._login()
        return self._token

    async def _request(self, endpoint: str, params: dict | None = None) -> dict:
        """Make an authenticated GET request, re-logging in on auth failure."""
        client = await self._ensure_client()
        token = await self._get_token()
        all_params = {"token": token, **(params or {})}
        resp = await client.get(f"{BASE_URL}/{endpoint}", params=all_params)
        resp.raise_for_status()
        data = resp.json()
        # Re-login on token expiry
        if data.get("response", {}).get("status", "").startswith("ERROR"):
            self._token = None
            token = await self._login()
            all_params["token"] = token
            resp = await client.get(f"{BASE_URL}/{endpoint}", params=all_params)
            resp.raise_for_status()
            data = resp.json()
        return data.get("response", {})

    async def _post_request(self, endpoint: str, data: dict | None = None) -> dict:
        """Make an authenticated POST request, re-logging in on auth failure."""
        client = await self._ensure_client()
        token = await self._get_token()
        all_data = {"token": token, **(data or {})}
        resp = await client.post(f"{BASE_URL}/{endpoint}", data=all_data)
        resp.raise_for_status()
        result = resp.json()
        # Re-login on token expiry
        if result.get("response", {}).get("status", "").startswith("ERROR"):
            self._token = None
            token = await self._login()
            all_data["token"] = token
            resp = await client.post(f"{BASE_URL}/{endpoint}", data=all_data)
            resp.raise_for_status()
            result = resp.json()
        return result.get("response", {})

    async def get_accounts(self) -> list[dict]:
        resp = await self._request("accounts")
        return resp.get("accounts", [])

    async def get_transactions(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        account_name: str | None = None,
        tag_name: str | None = None,
        status: str | None = None,
        page: int = 1,
    ) -> dict:
        params: dict = {"page": str(page)}
        if start_date:
            params["startDate"] = start_date
        if end_date:
            params["endDate"] = end_date
        if account_name:
            params["accountName"] = account_name
        if tag_name:
            params["tagName"] = tag_name
        if status:
            params["status"] = status
        resp = await self._request("transactions", params)
        return {
            "transactions": resp.get("transactions", []),
            "totalTransactions": int(resp.get("numTransactions", 0)),
        }

    async def get_all_transactions(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        account_name: str | None = None,
        tag_name: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        """Fetch all pages of transactions for a query."""
        all_txs = []
        page = 1
        while True:
            result = await self.get_transactions(
                start_date=start_date,
                end_date=end_date,
                account_name=account_name,
                tag_name=tag_name,
                status=status,
                page=page,
            )
            txs = result["transactions"]
            all_txs.extend(txs)
            total = result["totalTransactions"]
            if len(all_txs) >= total or len(txs) == 0:
                break
            page += 1
        return all_txs

    async def get_budgets(self) -> list[dict]:
        resp = await self._request("budgets")
        return resp.get("budgets", [])

    async def get_tags(self) -> list[dict]:
        resp = await self._request("tags")
        return resp.get("tags", [])

    async def edit_transaction(
        self,
        transaction_id: int,
        tags: str | None = None,
    ) -> dict:
        """Edit a transaction. Currently supports updating tags."""
        data: dict = {"id": str(transaction_id)}
        if tags is not None:
            data["tags"] = tags
        return await self._post_request("transaction_edit", data)


buxfer = BuxferClient()

# --- MCP Tools ---


@mcp.tool()
async def get_accounts() -> list[dict]:
    """List all Buxfer accounts with their current balances, bank names, and last sync times."""
    accounts = await buxfer.get_accounts()
    return [
        {
            "id": a["id"],
            "name": a["name"],
            "bank": a.get("bank", ""),
            "balance": a.get("balance", 0),
            "currency": a.get("currency"),
            "lastSynced": a.get("lastSynced"),
        }
        for a in accounts
    ]


@mcp.tool()
async def get_transactions(
    start_date: str | None = None,
    end_date: str | None = None,
    account_name: str | None = None,
    tag_name: str | None = None,
    status: str | None = None,
    page: int = 1,
) -> dict:
    """Fetch transactions with optional filters.

    Args:
        start_date: Start date in YYYY-MM-DD format (default: 30 days ago)
        end_date: End date in YYYY-MM-DD format (default: today)
        account_name: Filter by account name
        tag_name: Filter by tag name
        status: Filter by status: pending, reconciled, or cleared
        page: Page number for pagination (25 transactions per page)
    """
    return await buxfer.get_transactions(
        start_date=start_date,
        end_date=end_date,
        account_name=account_name,
        tag_name=tag_name,
        status=status,
        page=page,
    )


@mcp.tool()
async def get_budgets() -> list[dict]:
    """Get all budgets with their current spending status — limit, spent, remaining balance, and period."""
    budgets = await buxfer.get_budgets()
    return [
        {
            "id": b["id"],
            "name": b["name"],
            "limit": b.get("limit", 0),
            "spent": b.get("spent", b.get("balance", 0)),
            "balance": b.get("balance", 0),
            "period": b.get("period", "monthly"),
            "currentPeriod": b.get("currentPeriod"),
        }
        for b in budgets
    ]


@mcp.tool()
async def get_tags() -> list[dict]:
    """List all transaction tags. Tags are used to categorize transactions (e.g., Food, Transport, Entertainment)."""
    return await buxfer.get_tags()


@mcp.tool()
async def edit_transaction(
    transaction_id: int,
    tags: str | None = None,
) -> dict:
    """Edit a transaction's tags.

    Args:
        transaction_id: The numeric ID of the transaction to edit
        tags: Comma-separated list of tag names to assign (e.g. "Food, Groceries"). Pass an empty string to clear all tags.
    """
    if tags is None:
        raise ValueError("Provide 'tags' to update (use empty string to clear tags)")
    resp = await buxfer.edit_transaction(transaction_id=transaction_id, tags=tags)
    return {"status": resp.get("status", "OK"), "transaction_id": transaction_id, "tags": tags}


@mcp.tool()
async def financial_report(
    start_date: str | None = None,
    end_date: str | None = None,
) -> dict:
    """Generate a combined financial report for a date range — includes accounts, all transactions, budgets, and tags in a single call.

    Best used for weekly/monthly overviews, trend analysis, and identifying spending patterns.
    Fetches ALL pages of transactions for the given range automatically.

    Args:
        start_date: Start date in YYYY-MM-DD format (default: 30 days ago)
        end_date: End date in YYYY-MM-DD format (default: today)
    """
    if not start_date:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Fetch everything in parallel-ish (sequential due to shared token, but clean)
    accounts = await buxfer.get_accounts()
    transactions = await buxfer.get_all_transactions(
        start_date=start_date, end_date=end_date
    )
    budgets = await buxfer.get_budgets()
    tags = await buxfer.get_tags()

    # Compute summary stats
    total_income = sum(
        t["amount"] for t in transactions if t.get("type") == "income"
    )
    total_expenses = sum(
        abs(t["amount"]) for t in transactions if t.get("type") == "expense"
    )

    # Spending by tag
    spending_by_tag: dict[str, float] = {}
    for t in transactions:
        if t.get("type") == "expense":
            tag = t.get("tags") or "Untagged"
            # Tags can be comma-separated
            for single_tag in tag.split(","):
                single_tag = single_tag.strip()
                spending_by_tag[single_tag] = spending_by_tag.get(single_tag, 0) + abs(
                    t["amount"]
                )

    # Spending by account
    spending_by_account: dict[str, float] = {}
    for t in transactions:
        if t.get("type") == "expense":
            acct = t.get("accountName") or str(t.get("accountId", "Unknown"))
            spending_by_account[acct] = spending_by_account.get(acct, 0) + abs(
                t["amount"]
            )

    # Sort by amount descending
    spending_by_tag = dict(
        sorted(spending_by_tag.items(), key=lambda x: x[1], reverse=True)
    )
    spending_by_account = dict(
        sorted(spending_by_account.items(), key=lambda x: x[1], reverse=True)
    )

    return {
        "period": {"start": start_date, "end": end_date},
        "summary": {
            "total_income": total_income,
            "total_expenses": total_expenses,
            "net": total_income - total_expenses,
            "transaction_count": len(transactions),
            "spending_by_tag": spending_by_tag,
            "spending_by_account": spending_by_account,
        },
        "accounts": [
            {
                "id": a["id"],
                "name": a["name"],
                "bank": a.get("bank", ""),
                "balance": a.get("balance", 0),
                "currency": a.get("currency"),
            }
            for a in accounts
        ],
        "budgets": [
            {
                "id": b["id"],
                "name": b["name"],
                "limit": b.get("limit", 0),
                "spent": b.get("spent", b.get("balance", 0)),
                "balance": b.get("balance", 0),
                "period": b.get("period", "monthly"),
            }
            for b in budgets
        ],
        "transactions": transactions,
        "tags": tags,
    }


# --- Entrypoint ---

if __name__ == "__main__":
    import sys
    import uvicorn

    if "--sse" in sys.argv:
        port = int(os.environ.get("PORT", "8000"))
        uvicorn.run(mcp.sse_app(), host="0.0.0.0", port=port)
    else:
        mcp.run(transport="stdio")
