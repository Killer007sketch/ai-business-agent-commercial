from api.webhooks import extract_latest_reply_text
from config.business_config import get_business_config
from services.email_service import valid_email
from services.opportunity_filter import score_opportunity


def test_opportunity_filter_shortlists_strong_fit_without_llm():
    score, status, reasons = score_opportunity(
        {
            "title": "Build n8n automation with API webhooks",
            "problem": "Automate CRM lead routing and Slack notifications",
            "requirements": ["n8n", "CRM", "API", "webhook"],
            "budget_max_usd": 500,
        }
    )

    assert score >= 70
    assert status == "shortlist"
    assert reasons


def test_business_config_loads_required_sections():
    config = get_business_config()

    assert config["business"]["name"]
    assert config["offer"]["name"]
    assert config["proposal_agent"]["max_opportunities"] <= 5
    assert config["manager"]["use_llm_for_routine_decisions"] is False


def test_email_validation_is_deterministic():
    assert valid_email("buyer@example.com") is True
    assert valid_email("not-an-email") is False


def test_latest_reply_excludes_quoted_thread():
    text = "Thanks, that works.\n\nOn Monday Someone wrote:\n> Older message"
    assert extract_latest_reply_text(text) == "Thanks, that works."
