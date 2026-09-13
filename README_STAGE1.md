# AI Business Agent Starter Kit — Commercial Edition, Stage 1

This is the first clean commercial core.

Included:
- FastAPI application
- isolated settings
- SQLAlchemy database layer
- Opportunity model
- zero-LLM deterministic opportunity filter
- create/list opportunity API
- SQLite fallback for local testing
- PostgreSQL-compatible DATABASE_URL

No OpenAI calls are made in Stage 1.

## Run

1. Copy `.env.example` to `.env` and export the variables, or set them in your host.
2. Install:

   pip install -r requirements.txt

3. Start:

   uvicorn app:app --reload

4. Test:

   GET /health

5. Create an opportunity:

   POST /opportunities

Example JSON:

{
  "source": "manual",
  "title": "Need n8n CRM automation",
  "budget_text": "$500 fixed",
  "budget_min_usd": 500,
  "budget_max_usd": 500,
  "problem": "Automate lead intake, CRM sync and follow-up",
  "requirements": ["n8n", "CRM", "API", "email"]
}
