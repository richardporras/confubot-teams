# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Confubot Teams is a Microsoft Teams chatbot that answers questions using Azure Cognitive Search (hybrid keyword + vector search) and Azure OpenAI. It serves as a technical assistant for internal Confluence documentation.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally (default port 8000)
python app.py

# Run with custom port
PORT=3000 python app.py
```

## Architecture

The application is a single-file Quart async web server (`app.py`) with two main endpoints:

- **`POST /api/messages`** - Microsoft Bot Framework endpoint for Teams integration. Receives activities from Teams, processes messages through `BotFrameworkAdapter`.
- **`POST /api/ask`** - REST API endpoint with Basic Auth for MCP (Model Context Protocol) clients. Returns OpenAI-compatible chat completion format.

### Request Flow

1. User query received → `detect_intent()` classifies as resumen/extraccion/procedimiento/consulta_directa
2. `search_azure_hybrid()` performs combined keyword + vector search against Azure Cognitive Search
3. `build_context()` assembles search results into a prompt context (max 60k chars)
4. `generate_openai_response()` calls Azure OpenAI with intent-specific system prompts
5. Response includes answer + source links with relevance scores

### Key Components

- **Intent Detection**: Uses Azure OpenAI to classify queries, with local fallback (`detect_intent_local`)
- **Hybrid Search**: Combines BM25 keyword search with vector similarity using text-embedding-3-large (1536 dimensions)
- **Bot Adapter**: Configured for single-tenant Azure AD authentication

## Environment Variables

Required:
- `BOT_APP_ID`, `BOT_APP_SECRET`, `BOT_TENANT_ID` - Azure Bot registration
- `AZURE_SEARCH_SERVICE`, `AZURE_SEARCH_API_KEY`, `AZURE_SEARCH_INDEX` - Azure Cognitive Search
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_DEPLOYMENT` - Azure OpenAI

Optional:
- `BASIC_AUTH_USER`, `BASIC_AUTH_PASS` - Credentials for `/api/ask` endpoint
- `MIN_SCORE_THRESHOLD_HYBRID` - Minimum score for hybrid search results (default: 0.01)
- `MIN_SCORE_THRESHOLD` - Minimum score for classic keyword search (default: 10)
- `PORT` - Server port (default: 8000)

## Deployment

- **main branch** → Azure Web App `confubot-teams-pro` (Production)
- **develop branch** → Azure Web App `confubot-teams` (Development)

CI/CD uses GitHub Actions with Azure OIDC authentication.
