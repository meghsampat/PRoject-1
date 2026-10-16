"""Rule-based local Supervisor. Supports explicit demo question patterns only."""
import re
from src import config
from src.agents import customer_product_agent, data_science_agent, forecast_agent

ROUTES = {
    "sales_kpis": ("Data Science Agent", "query_sales_kpis"),
    "sales_trend": ("Data Science Agent", "get_sales_trend"),
    "week_diagnosis": ("Data Science Agent", "get_week_diagnosis"),
    "top_products": ("Data Science Agent", "get_product_performance"),
    "category_intelligence": ("Data Science Agent", "get_category_intelligence"),
    "customer_segments": ("Customer/Product Analytics Agent", "get_customer_segments"),
    "forecast": ("Forecast & Recommendation Agent", "forecast_demand"),
    "recommendations": ("Forecast & Recommendation Agent", "get_recommendations"),
}
PATTERNS = {
    "sales_kpis": r"(?:what are (?:the )?sales kpis|show (?:the )?sales kpis|sales kpis|kpis)",
    "sales_trend": r"(?:show (?:the )?weekly sales trend|weekly sales trend|what happened to weekly sales)",
    "top_products": r"(?:show (?:the )?top products|top products|which products perform best)",
    "category_intelligence": r"(?:show (?:the )?category intelligence|category intelligence|which categories have the highest intelligence scores)",
    "week_diagnosis": rf"(?:investigate (?:sales (?:in )?)?week {config.DIAG_TARGET_WEEK}|show (?:the )?week {config.DIAG_TARGET_WEEK} diagnosis|what happened (?:in )?week {config.DIAG_TARGET_WEEK})",
    "recommendations": r"(?:which (?:products|categories) should we promote (?:next month|(?:the )?next (?:4|four) weeks)|show (?:the )?promotion recommendations|show (?:the )?recommendation rankings)",
    "customer_segments": r"(?:show (?:the )?customer segments|customer segments|segment customers)",
}


def route_question(question):
    if not isinstance(question, str) or not question.strip():
        raise ValueError("Enter a manager question.")
    normalized = " ".join(question.lower().strip().rstrip("?.!").split())
    intent = None
    category = None
    for name, pattern in PATTERNS.items():
        if re.fullmatch(pattern, normalized):
            intent = name
            break
    forecast = re.fullmatch(r"forecast (.+?) (?:demand|revenue|sales) (?:for )?(?:next month|(?:the )?next (?:4|four) weeks)", normalized)
    if forecast:
        intent, category = "forecast", forecast.group(1)
        # Do not silently accept modifiers or a second task as part of a category.
        if re.search(r"\b(?:and|then|but|for|in|from|to)\b", category):
            raise ValueError("Ask one supported question at a time, with a commodity category and sidebar week scope.")
    if intent is None:
        raise ValueError("This rule-based prototype supports sales KPIs, weekly sales trend, week diagnosis, top products, category intelligence (full window), customer segments, recommendation rankings (full window), and 'Forecast <commodity> revenue for next month'. Use a demo question; extra customer, location, or date filters are not supported. Set week scope in the sidebar.")
    specialist, tool = ROUTES[intent]
    return {"intent": intent, "specialist": specialist, "tool": tool,
            "category": category, "method": "Rule-based full-question matching; no LLM",
            "reason": f"Matched supported {intent.replace('_', ' ')} question pattern."}


def run_specialist(decision, data, products, start_week, end_week):
    intent = decision["intent"]
    if intent in {"sales_kpis", "sales_trend", "top_products", "category_intelligence", "week_diagnosis"}:
        return data_science_agent.answer(intent, data, products, start_week, end_week)
    if intent == "customer_segments":
        return customer_product_agent.answer(intent, data, products, start_week, end_week)
    if intent in {"forecast", "recommendations"}:
        return forecast_agent.answer(intent, data, products, start_week, end_week, decision["category"])
    raise ValueError("Supervisor selected an unsupported intent.")



