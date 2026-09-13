def _safe_int(value):
    try:
        if value is None or value == "":
            return None
        return int(float(value))
    except Exception:
        return None


def score_opportunity(opportunity: dict):
    """
    Zero-LLM deterministic filter.

    Returns:
        (score, status, reasons)
    """
    text = " ".join([
        str(opportunity.get("title") or ""),
        str(opportunity.get("problem") or ""),
        " ".join(str(x) for x in (opportunity.get("requirements") or [])),
    ]).lower()

    score = 35
    reasons = []

    strong_terms = {
        "n8n": 15,
        "automation": 10,
        "workflow": 8,
        "api": 8,
        "webhook": 8,
        "crm": 8,
        "openai": 7,
        "llm": 7,
        "ai agent": 8,
        "google sheets": 5,
        "slack": 5,
        "email": 4,
        "lead": 5,
        "hubspot": 5,
        "zapier": 5,
        "make.com": 5,
        "rag": 6,
        "chatbot": 5,
    }

    matched = []
    for term, points in strong_terms.items():
        if term in text:
            score += points
            matched.append(term)

    if matched:
        reasons.append("stack_match: " + ", ".join(matched[:8]))

    budget_min = _safe_int(opportunity.get("budget_min_usd"))
    budget_max = _safe_int(opportunity.get("budget_max_usd"))
    effective_budget = budget_max if budget_max is not None else budget_min

    if effective_budget is not None:
        if effective_budget >= 1000:
            score += 15
            reasons.append("budget>=1000")
        elif effective_budget >= 500:
            score += 10
            reasons.append("budget>=500")
        elif effective_budget >= 200:
            score += 5
            reasons.append("budget>=200")
        elif effective_budget < 100:
            score -= 15
            reasons.append("budget<100")
    else:
        reasons.append("budget_unknown")

    risky_terms = {
        "on-site": 25,
        "onsite": 25,
        "full-time": 12,
        "full time": 12,
        "medical diagnosis": 25,
        "legal advice": 25,
        "hardware": 15,
        "mobile app from scratch": 10,
        "blockchain": 8,
    }

    for term, penalty in risky_terms.items():
        if term in text:
            score -= penalty
            reasons.append("penalty:" + term)

    score = max(0, min(100, score))

    if score >= 70:
        status = "shortlist"
    elif score >= 55:
        status = "review_later"
    else:
        status = "skip"

    return score, status, reasons
