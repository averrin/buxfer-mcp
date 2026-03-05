# Buxfer MCP Server

MCP server for the [Buxfer](https://www.buxfer.com/) personal finance API. Exposes accounts, transactions, budgets, tags, and combined financial reports to any MCP-compatible AI client.

## Tools

| Tool | Description |
|---|---|
| `get_accounts` | List all accounts with balances |
| `get_transactions` | Fetch transactions with filters (date range, account, tag, status) |
| `get_budgets` | Budget status — limit, spent, remaining |
| `get_tags` | All transaction tags |
| `financial_report` | Combined report: accounts + all transactions + budgets + tags + spending summaries for a date range |

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure credentials
cp .env.example .env
# Edit .env with your Buxfer email and password

# Run locally
python server.py
```

The server starts on `http://localhost:8000/sse`.

## Docker / Coolify

```bash
docker build -t buxfer-mcp .
docker run -p 8000:8000 \
  -e BUXFER_EMAIL=your@email.com \
  -e BUXFER_PASSWORD=your_password \
  buxfer-mcp
```

On Coolify, set `BUXFER_EMAIL` and `BUXFER_PASSWORD` as environment variables in the service configuration. Expose port 8000.

## MCP Client Configuration

Add to your MCP client config (e.g. Claude Desktop, Gemini CLI):

```json
{
  "mcpServers": {
    "buxfer": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

For Coolify deployment, replace `localhost:8000` with your service URL.
