# Firecrawl Demo

This project demonstrates how to use Firecrawl's powerful web scraping and data extraction features from Python, following the official documentation at <https://docs.firecrawl.dev/introduction>.

## Features Demonstrated

- **Scraping**: Extract clean markdown and HTML from any URL
- **JSON Mode**: Get structured data using Pydantic schemas or AI prompts
- **Crawling**: Automatically discover and scrape entire websites
- **Search**: Perform web searches and get full content from results
- **Extract**: Get AI-powered data extraction from web pages
- **Actions**: Interact with pages before scraping (clicks, input, etc.)

## Setup

1. **Install Firecrawl Python package**:

   ```bash
   pip install firecrawl-py
   ```

2. **Set up your API key**:
   - Sign up at [firecrawl.dev](https://firecrawl.dev)
   - Get your API key
   - Add it to `.env` file:

     ```env
     FIRECRAWL_API_KEY=fc-your-api-key-here
     ```

3. **Run the demonstrations**:

   **Basic demo** (simple scrape and extract):

   ```bash
   python main.py
   ```

   **Comprehensive examples** (all features):

   ```bash
   python examples.py
   ```

## Files

- `main.py` - Simple demonstration of scraping and extracting
- `examples.py` - Comprehensive showcase of all Firecrawl features
- `.env` - Your API key configuration

## Key Features

### Scraping

```python
from firecrawl import Firecrawl

client = Firecrawl(api_key="your-api-key")
result = client.scrape("https://example.com", formats=["markdown"])
print(result.markdown)
```

### JSON Mode with Schema

```python
from pydantic import BaseModel

class CompanyInfo(BaseModel):
    name: str
    description: str

result = client.scrape(
    'https://example.com',
    formats=[{"type": "json", "schema": CompanyInfo}]
)
```

### Crawling

```python
docs = client.crawl(url="https://example.com", limit=10)
```

### Search

```python
results = client.search(query="your search term", limit=5)
```

## Documentation

For complete API documentation and advanced features, visit:

- [Official Docs](https://docs.firecrawl.dev)
- [Python SDK Guide](https://docs.firecrawl.dev/sdks/python)
- [API Reference](https://docs.firecrawl.dev/api-reference/introduction)

## Advanced MCP Configuration

The workspace `.vscode/mcp.json` now exposes optional inputs so you can tune the official `firecrawl-mcp` server without editing code. When VS Code prompts for a value you can leave it blank to keep Firecrawl defaults.

- `FIRECRAWL_API_URL`: Point the MCP server at a self-hosted Firecrawl instance.
- `FIRECRAWL_RETRY_MAX_ATTEMPTS`, `FIRECRAWL_RETRY_INITIAL_DELAY`, `FIRECRAWL_RETRY_MAX_DELAY`, `FIRECRAWL_RETRY_BACKOFF_FACTOR`: Control exponential backoff behaviour.
- `FIRECRAWL_CREDIT_WARNING_THRESHOLD`, `FIRECRAWL_CREDIT_CRITICAL_THRESHOLD`: Configure credit-usage alerts when using the hosted API.

After updating values, run the VS Code command `MCP: List Servers`, pick `firecrawl`, and choose **Restart** so the new environment settings take effect.
