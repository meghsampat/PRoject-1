"""Short, detailed and action views derived from the same checked evidence."""
import math
from src import config


def short_summary(response):
    e, tool = response["evidence"], response["tool"]
    if tool == "query_sales_kpis":
        return (f"Revenue is USD {e['revenue']:,.2f} from {e['baskets']:,} baskets. "
                f"Average basket value is USD {e['average_basket_value']:,.2f}.")
    if tool == "get_sales_trend":
        return f"Recorded revenue totals USD {e['revenue']:,.2f} across {len(e['rows'])} observed weeks. Partial weeks can distort comparisons."
    if tool == "get_product_performance":
        row = e["rows"][0]
        return f"Product {row['PRODUCT_ID']} leads by revenue: USD {row['revenue']:,.2f} ({row['COMMODITY_DESC']}). Revenue leadership does not establish profit."
    if tool == "get_category_intelligence":
        row = e["rows"][0]
        return f"{row['COMMODITY_DESC']} leads the category index at {row['score']:.2f}/100. This is a descriptive priority, not promotion lift."
    if tool == "get_customer_segments":
        return f"The analysis groups {e['households']:,} households into {e['chosen_k']} segments. Their business names and actions remain provisional."
    if tool == "get_week_diagnosis":
        return f"Week {e['week']} revenue is USD {e['revenue']:,.2f}, {e['revenue_change_pct']:+.2f}% versus the surrounding-week mean. The cause remains unknown; records are retained."
    if tool == "forecast_demand":
        return f"The revenue outlook for {e['category']} is USD {e['forecast_total']:,.2f} over {e['forecast_horizon']} dataset weeks. It is not a physical-unit forecast or a future guarantee."
    if tool == "get_recommendations":
        promote = sorted([row for row in e["rows"] if row["candidate"] == "forecast"
                          and row["priority_label"] == "promote"
                          and row["execution_status"] == "review_required"], key=lambda row: row["rank"])
        if promote:
            return f"Review {promote[0]['COMMODITY_DESC']} as a forecast-based promotion test candidate. Both ranking lists require review; no campaign or ROI is established."
        return "The two rankings provide category priorities for review. No forecast-list candidate shown has a promote label; no campaign or ROI is established."
    raise ValueError("No short summary exists for this analysis.")


def answer_views(response, blocks, focus="summary"):
    lookup = {block["id"]: block for block in blocks}
    caveat = lookup["limitations"]["text"]
    short = short_summary(response)
    if focus == "explain":
        short = lookup["explanation"]["text"]
    elif focus == "risks":
        short = caveat
    elif focus == "suggestions":
        short = "Review these next steps using the current evidence. Treat them as proposals, not approved actions."
    actions = [block["text"] for block in blocks if block["kind"] == "suggestion"]
    parts = [block["text"] for block in blocks if block["kind"] == "fact"]
    e = response["evidence"]
    if response["tool"] == "forecast_demand":
        metrics = e.get("four_week_evaluation") or e["evaluation"]
        title = "Four-week-total held-out comparison" if e.get("four_week_evaluation") else "One-step held-out comparison"
        lines = ["**" + title + "**", "", "| Method | WAPE (error) |", "| --- | ---: |"]
        for row in metrics:
            value = row["WAPE_pct"]
            error = f"{value:.2f}%" if value is not None and math.isfinite(value) else "Undefined"
            lines.append(f"| {row['model']} | {error} |")
        parts.append("\n".join(lines))
        parts.append("Methods use the matched holdout for this analysis. WAPE measures error, not accuracy; holdout results do not guarantee future performance.")
    if actions:
        parts.append("**What to do next**\n\n" + "\n".join(f"{index}. {action}" for index, action in enumerate(actions, 1)))
    parts.append(caveat)
    parts.append("**Data used:** " + e["scope"] + "\n\n**Revenue basis:** " + e["revenue_definition"])
    detailed = "\n\n".join(parts)
    export = "**Short answer**\n\n" + short + "\n\n**Detailed answer**\n\n" + detailed
    return {"short_answer": short, "detailed_answer": detailed, "next_steps": actions,
            "caveat": caveat, "export_markdown": export}
