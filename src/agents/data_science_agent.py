"""Readable template specialist; analytics are delegated to tools."""
from src import tools
from src.answer_templates import render_answer


def answer(intent, data, products, start_week, end_week):
    if intent == "sales_kpis":
        evidence = tools.query_sales_kpis(data, start_week, end_week)
        fields, tool = ["revenue", "baskets", "households", "average_basket_value"], "query_sales_kpis"
    elif intent == "sales_trend":
        evidence = tools.get_sales_trend(data, start_week, end_week)
        fields, tool = ["revenue"], "get_sales_trend"
    elif intent == "top_products":
        evidence = tools.get_product_performance(data, products, start_week, end_week)
        fields, tool = ["products_shown"], "get_product_performance"
    elif intent == "week_diagnosis":
        evidence = tools.get_week_diagnosis(data, start_week, end_week)
        fields, tool = ["revenue", "reference_revenue", "revenue_change_pct"], "get_week_diagnosis"
    elif intent == "category_intelligence":
        evidence = tools.get_category_intelligence(data, start_week, end_week)
        fields, tool = ["categories_shown", "categories_scored", "top_score"], "get_category_intelligence"
    else:
        raise ValueError("Data Science specialist received an unsupported intent.")
    return {"specialist": "Data Science Agent", "tool": tool,
            "answer": render_answer(tool, evidence),
            "claims": {key: evidence[key] for key in fields}, "evidence": evidence}


