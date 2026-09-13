# AI Business Agent Starter Kit — Commercial Edition, Stage 2

Stage 2 adds a reusable commercial policy layer without hardcoded business names,
prices, timelines, or scope.

## Included

- Everything from Stage 1
- `config/business.yaml` — buyer-editable business, offer, scope, autonomy, and risk policy
- `config/business_config.py` — validated YAML loader
- `agents/business_manager.py` — config-driven commercial policy + deterministic risk gate
- High-risk requests escalate before any model call
- Routine Business Manager LLM use is **disabled by default**

## OpenAI cost behavior

With the default `config/business.yaml`:

- Opportunity filter: **0 OpenAI calls**
- Business Manager standard decision: **0 OpenAI calls**
- Business Manager high-risk escalation: **0 OpenAI calls**

To enable optional LLM-assisted selection of a routine next action, set:

```yaml
manager:
  use_llm_for_routine_decisions: true
```

and provide `OPENAI_API_KEY`.

## Customize the product

Edit only `config/business.yaml` to change:

- business name
- offer name
- price and currency
- maximum delivery timeline
- approved/excluded scope
- autonomous actions
- risk patterns
- Business Manager model behavior

The Python agent does not contain ReplyOps AI, the old $49 pilot, or the old
14-day product rules.

## Run

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Then test:

```text
GET /health
```

## Quick local Business Manager check

```bash
python -c "from agents.business_manager import BusinessManagerAgent; print(BusinessManagerAgent().decide('What is included?'))"
```

That command makes zero OpenAI calls with the default configuration.
