# AI Business Agent Starter Kit

A modular FastAPI starter kit for building AI-assisted business workflows around opportunity intake, deterministic filtering, proposal generation, conversation handling, risk gating, and optional email automation.

## What is included

- FastAPI application with OpenAPI docs
- SQLAlchemy persistence with SQLite by default and PostgreSQL support
- Zero-LLM opportunity scoring/filtering
- Proposal Agent with dry-run mode and a maximum of one OpenAI call per generation request
- Conversation Agent with persisted history
- Deterministic Business Manager / risk gate
- Optional Resend inbound webhook and outbound email adapter
- Safe email defaults: inbound analysis and auto-reply are disabled until explicitly enabled
- Docker and Docker Compose setup
- Pytest smoke/core tests

## Project layout

```text
agents/      AI/business decision modules
api/         FastAPI routers
config/      business and runtime configuration
database/    SQLAlchemy engine/session setup
models/      database models
services/    deterministic and provider services
tests/       automated tests
app.py       FastAPI entry point
```

## Quick start — local Python

### 1. Create a virtual environment

```bash
python -m venv .venv
```

Activate it using the command for your operating system.

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

For development/testing:

```bash
pip install -r requirements-dev.txt
```

### 3. Configure environment

Copy `.env.example` to `.env` and set only the variables you need.

The application works with SQLite and the deterministic opportunity filter without an OpenAI key.

Important: this project reads environment variables from the process environment. If you use a `.env` file locally, load/export it with your preferred environment manager or Docker Compose.

### 4. Start the API

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Open:

- API docs: `http://localhost:8000/docs`
- Health check: `http://localhost:8000/health`

## Quick start — Docker Compose

```bash
docker compose up --build
```

This starts:

- API on port `8000`
- PostgreSQL on the internal Docker network

The Compose file uses development credentials. Replace them before exposing a deployment publicly.

## Business configuration

Edit `config/business.yaml` to customize:

- business name
- offer name and price
- delivery timeline
- approved/excluded scope
- allowed autonomous actions
- forbidden/high-risk actions
- Proposal Agent limits
- Conversation Agent limits

You can point to another YAML file with:

```bash
BUSINESS_CONFIG_PATH=/absolute/path/to/business.yaml
```

## Core API workflow

### 1. Create an opportunity

`POST /opportunities`

Example JSON:

```json
{
  "source": "marketplace",
  "title": "Build an n8n lead routing workflow",
  "source_url": "https://example.com/job/123",
  "budget_max_usd": 500,
  "problem": "Route incoming leads to the right sales rep and notify Slack.",
  "requirements": ["n8n", "webhook", "Slack"]
}
```

This step uses the deterministic Python filter and makes **0 OpenAI calls**.

### 2. Preview Proposal Agent input

`POST /proposals/generate`

```json
{
  "opportunity_ids": [1],
  "dry_run": true
}
```

Dry-run mode makes **0 OpenAI calls**.

### 3. Generate a proposal

Use the same endpoint with:

```json
{
  "opportunity_ids": [1],
  "dry_run": false
}
```

This requires `OPENAI_API_KEY` and makes at most **1 OpenAI call per request**.

### 4. Analyze a customer message

`POST /conversations/analyze`

Use `dry_run: true` first to inspect deterministic behavior without an OpenAI call.

## OpenAI cost controls

The starter kit is designed so that routine ingestion/filtering can run without LLM cost.

- Opportunity filter: 0 OpenAI calls
- Proposal dry run: 0 OpenAI calls
- Proposal generation: maximum 1 OpenAI call per request
- Business Manager routine decisions: deterministic by default
- Inbound email analysis: disabled by default
- Email auto-reply: disabled by default

To keep costs predictable, leave optional LLM features disabled until you intentionally enable them.

## Email / Resend integration

Required environment variables for email integration:

```text
RESEND_API_KEY
RESEND_WEBHOOK_SECRET
EMAIL_FROM_ADDRESS
EMAIL_FROM_NAME
```

Webhook endpoint:

```text
POST /webhooks/resend
```

Safe defaults:

```text
EMAIL_ANALYZE_INBOUND=false
EMAIL_AUTO_REPLY=false
```

With these defaults, a valid inbound email can be stored without calling OpenAI or sending an automatic reply.

Only enable automated sending for communication you are authorized to send and in compliance with the provider/platform rules that apply to your use case.

## Database

Default local database:

```text
sqlite:///./commercial.db
```

Example PostgreSQL URL:

```text
postgresql+psycopg2://user:password@localhost:5432/ai_business_agent
```

Set it with `DATABASE_URL`.

## Run tests

```bash
pytest -q
```

The included tests do not make real OpenAI or Resend API calls.

## Production checklist

Before production deployment:

1. Change example business settings in `config/business.yaml`.
2. Use PostgreSQL rather than the default local SQLite database for a multi-instance deployment.
3. Store secrets only in the deployment platform's secret/environment manager.
4. Keep `EMAIL_AUTO_REPLY=false` until inbound handling has been tested with your own rules.
5. Put the API behind HTTPS and appropriate authentication/network controls.
6. Review the risk patterns and autonomous-action policy for your business.
7. Run the test suite after every configuration/code change.

## Notes

This repository is a developer starter kit, not a finished vertical SaaS product. Authentication, billing, a frontend, marketplace-specific submission automation, and customer-specific compliance controls are intentionally not included in the core.
