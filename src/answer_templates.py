"""Fixed summaries derived solely from structured tool evidence."""


def render_answer(tool, evidence):
    if tool == "query_sales_kpis":
        return (f"Revenue is ${evidence['revenue']:,.2f} across {evidence['baskets']:,} baskets "
                f"and {evidence['households']:,} households. Average basket value is ${evidence['average_basket_value']:,.2f} (USD).")
    if tool == "get_sales_trend":
        return f"Observed weekly sales total ${evidence['revenue']:,.2f} (USD). The chart shows the selected period; partial weeks can distort comparisons. This trend does not establish causes."
    if tool == "get_week_diagnosis":
        pattern = ("Changes span stores and major departments; retain the observed records. The cause remains unverified."
                   if evidence["breadth"]["broad_pattern"] else
                   "Observed concentration needs review; retain records under the current cleaning policy. The cause remains unverified.")
        return (f"Week {evidence['week']} revenue is ${evidence['revenue']:,.2f}, versus ${evidence['reference_revenue']:,.2f} "
                f"for the neighbouring complete-week mean ({evidence['revenue_change_pct']:+.2f}%). " + pattern)
    if tool == "get_product_performance":
        return f"The table ranks {evidence['products_shown']} products by revenue in the selected scope. High revenue alone does not establish profitability."
    if tool == "get_category_intelligence":
        promotion_note = ("No scored category has a supported promotion comparison; its promotion component is neutral. "
                          if evidence.get("promotion_associations_available", 0) == 0
                          else "Unknown promotion comparisons receive a neutral component. ")
        return (f"The table shows the top {evidence['categories_shown']} of {evidence['categories_scored']} scored categories, "
                f"with a highest composite score of {evidence['top_score']:.2f} out of 100. "
                "This descriptive ranking combines sales scale, reach, repeat purchasing, buyer value and growth. "
                + promotion_note + "Weights are analyst choices; the index does not measure profit or causal promotion effects.")
    if tool == "get_customer_segments":
        if evidence.get("mode") == "saved_model":
            return (f"The saved RFM model assigns {evidence['households']:,} households to {evidence['chosen_k']} groups, "
                    f"with sampled silhouette {evidence['silhouette']:.3f}. Selection includes cluster-size and initialization-stability checks. "
                    "These are practical divisions of a customer continuum; business names and actions remain provisional.")
        return (f"Exploratory RFM clustering divides {evidence['households']:,} households into {evidence['chosen_k']} groups, "
                f"with sampled silhouette {evidence['silhouette']:.3f}. Selection uses silhouette and a minimum cluster size. "
                "Treat these groups as practical divisions of a customer continuum; stability and business interpretation remain pending for this period.")
    if tool == "get_recommendations":
        return (f"The two tables show {evidence['forecast_candidates_shown']} forecast-based and "
                f"{evidence['segment_candidates_shown']} segment-based category priorities for dataset weeks "
                f"{evidence['forecast_weeks'][0]}-{evidence['forecast_weeks'][-1]}. "
                f"The top lists share {evidence['top10_overlap_count']} category. "
                "Scores compare within each method. Promote means a provisional test candidate; "
                "human review is required. Promotion effects and ROI are unknown, and no automatic winner is chosen.")
    if tool == "forecast_demand":
        if evidence.get("mode") == "saved_direct_model":
            choices = "; ".join(f"h{h}: {method}" for h, method in evidence["chosen_methods"].items())
            return (f"For {evidence['category']}, the saved forecasting pipeline predicts ${evidence['forecast_total']:,.2f} "
                    f"in revenue (USD) across {evidence['forecast_horizon']} weeks after dataset week {evidence['origin_week']}. "
                    f"Methods chosen on earlier validation: {choices}. "
                    "Compare gradient boosting against naive, seasonal naive and moving-average holdout results below. "
                    "This is a revenue outlook; future accuracy and physical unit demand are not established.")
        return (f"For {evidence['category']}, the moving-average baseline forecasts ${evidence['forecast_total']:,.2f} "
                f"in revenue (USD) over {evidence['forecast_horizon']} weeks after dataset week {evidence['origin_week']}. "
                "This is a revenue outlook, not a unit-demand prediction. Compare the one-step holdout baseline results below; four-step accuracy has not been evaluated.")
    raise ValueError("No answer template exists for this tool.")






