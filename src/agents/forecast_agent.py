"""Forecast specialist serving validated saved models or explicit subperiod baselines."""
from src.answer_templates import render_answer
from src import tools


def answer(intent, data, products, start_week, end_week, category):
    if intent == "forecast":
        evidence = tools.forecast_demand(data, products, start_week, end_week, category)
        tool, fields = "forecast_demand", ["forecast_total", "forecast_horizon", "origin_week"]
    elif intent == "recommendations":
        evidence = tools.get_recommendations(data, start_week, end_week)
        tool, fields = "get_recommendations", ["forecast_candidates_shown", "segment_candidates_shown", "top10_overlap_count"]
    else:
        raise ValueError("Forecast specialist received an unsupported intent.")
    return {"specialist": "Forecast & Recommendation Agent", "tool": tool,
            "answer": render_answer(tool, evidence),
            "claims": {key:evidence[key] for key in fields}, "evidence": evidence}


