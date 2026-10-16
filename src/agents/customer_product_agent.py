"""Customer specialist delegates RFM clustering to the Python tool."""
from src.answer_templates import render_answer
from src.tools import get_customer_segments


def answer(intent, data, products, start_week, end_week):
    if intent != "customer_segments":
        raise ValueError("Customer specialist received an unsupported intent.")
    evidence = get_customer_segments(data, start_week, end_week)
    return {"specialist": "Customer/Product Analytics Agent", "tool": "get_customer_segments",
            "answer": render_answer("get_customer_segments", evidence),
            "claims": {key: evidence[key] for key in ["chosen_k", "silhouette", "households"]}, "evidence": evidence}
