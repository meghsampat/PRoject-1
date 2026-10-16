"""Review III slide wording: measured local implementation and labelled future assumptions."""
from src import config


def slide_plan(v, segment, category, recommendation):
    rule = v["rfm_rule_groups"]
    def rline(name):
        row = rule[name]
        return (f"{name}: {row['households']:,} households; {row['revenue_share_pct']:.2f}% of revenue; "
                f"mean window spend USD {row['mean_window_spend']:,.2f}.")
    group_sizes = "/".join(f"{row['households']:,}" for row in v["kmeans_groups"])
    top = [row["COMMODITY_DESC"] for row in v["top_categories"]]
    departments = ", ".join(row["department"] for row in v["top_departments"])
    gb, naive = v["horizon_metrics"]["Gradient boosting"], v["horizon_metrics"]["Naive"]
    totals = v["four_week_metrics"]
    plan = {
    2: ("Introduction", [
        "FMCG sales, customer, product and discount data can support repeatable retail decisions.",
        "The supplied POS files are prepared and validated locally; the accepted FMCG scope is documented.",
        "This dashboard combines KPI analysis, customer segmentation, revenue forecasting and category priorities.",
        "Supported chat questions return checked data, concise summaries, detailed explanations and proposed next steps.",
        "Review III status: the local workflow is operational. Human usefulness and recommendation-effectiveness reviews remain open."
    ]),
    3: ("Objectives and Verified Status", [
        "Conversational BI: supported local question patterns and remembered follow-ups are implemented; unknown requests are clarified.",
        "Data science: KPIs, RFM/K-Means, direct gradient-boosting forecasts with baselines, and category rankings are implemented.",
        "Evidence checks: the local deterministic Judge validates routing, claims and response consistency before display.",
        "Actions: separate forecast and spending-group priorities are available. Cross-sell/coupon effectiveness is not evaluated.",
        "Runtime: Streamlit runs in VS Code with its integrated browser. GCP and public deployment are excluded by the user."
    ]),
    4: ("Local System Architecture", [
        "Data: supplied dunnhumby CSV files remain on this computer; no cloud upload is performed.",
        "Preparation: validated Python joins, scope decisions and anomaly flags produce processed Parquet tables.",
        "Analytics: local RFM/K-Means, HistGradientBoosting, naive/seasonal-naive/moving-average baselines and category scores.",
        "Coordination: Supervisor routes one request to one of three specialists; the deterministic Judge checks evidence.",
        "Application: Streamlit chat, charts, short/detail answers and next steps, previewed inside VS Code.",
        "Reproducibility: source/model/configuration fingerprints, saved artifacts and independent validation reports."
    ]),
    5: ("Five Local Roles and Evidence Flow", [
        "Supervisor: maps supported questions to registered specialist/tool routes; unsupported filters and multiple tasks are declined.",
        "Data Science Agent: query_sales_kpis, get_sales_trend, get_product_performance, get_category_intelligence and get_week_diagnosis.",
        "Customer/Product Agent: get_customer_segments serves validated full-window RFM/K-Means profiles.",
        "Forecast/Recommendation Agent: forecast_demand and get_recommendations load validated saved evidence.",
        "Judge: validate_answer checks routing, scope, numeric claims and consistency; rejected output is withheld.",
        "Implementation: local Python modules and function calls. Google ADK AgentTools and a live language model are not used."
    ]),
    6: ("Dataset and Preprocessing", [
        f"Source: supplied dunnhumby POS data; {v['raw_households']:,} households and dataset days 1-711 before analysis-window selection.",
        "Product and household lookups are validated. Discount fields and prepared promotion-support records remain descriptive.",
        f"Cleaning removes only quantity=0 AND sales=0: {v['removed_joint_zero_rows']:,} lines. Other unusual records are retained and flagged.",
        f"Calendar dates are synthetic. Analysis starts at week {v['start_week']}; partial week {v['end_week']} is excluded from forecast training.",
        "Features include recorded USD revenue, observed discount flags, past-only weekly covariates and log1p RFM rates.",
        f"Retained master: {v['retained_master_rows']:,} rows. Approved weeks {v['start_week']}-{v['end_week']}: {v['analysis_rows']:,} analysis lines."
    ]),
    7: ("EDA and KPI Findings", [
        f"Approved-window revenue: USD {v['revenue_usd']:,.2f}; {v['baskets']:,} distinct baskets; {v['households']:,} households.",
        f"Complete-week peak: week {v['peak_week']}, USD {v['peak_week_revenue_usd']:,.2f}. Second-half mean weekly revenue is {v['second_half_mean_change_pct']:+.2f}% versus the first half.",
        f"Top departments: {departments}; combined revenue share {v['top_departments_revenue_share_pct']:.2f}%.",
        f"Average basket value: USD {v['average_basket_value_usd']:.2f}; mean baskets per household: {v['mean_baskets_per_household']:.2f} across the selected window.",
        f"Discounted-sales share: {v['discounted_sales_share_pct']:.2f}% of recorded revenue; any negative retail/coupon/coupon-match discount, not causal lift.",
        f"Policy window starts at week {v['start_week']}; forecasting uses {v['complete_weeks']} complete weeks ({v['first_complete_week']}-{v['last_complete_week']})."
    ]),
    8: ("Customer Segmentation: RFM and K-Means", [
        "R = days since last selected purchase; F = baskets/week observed; M = recorded revenue/week observed. Tenure is not verified.",
        "Features use log1p and StandardScaler in local scikit-learn; demographics are descriptive, not model inputs.",
        "K-Means candidates k=2..10; production seed 42. Minimum size and four-seed initialization agreement guard selection.",
        f"Selected k={v['chosen_k']}; silhouette {segment['silhouette']:.4f}; mean seed ARI {segment['stability_mean_ari']:.4f}. Temporal robustness remains unreviewed.",
        f"K-Means has {v['chosen_k']} groups ({group_sizes} households). The next slide separately reports four saved RFM RULE groups, not four clusters."
    ]),
    9: ("RFM Rule Baseline Results", [
        rline(config.REVIEW3_RULE_ORDER[0]),
        rline(config.REVIEW3_RULE_ORDER[1]),
        rline(config.REVIEW3_RULE_ORDER[2]),
        rline(config.REVIEW3_RULE_ORDER[3]),
        f"Rule baseline, not K-Means: the highest-revenue rule group has {v['largest_rule_household_share_pct']:.2f}% of households and {v['largest_rule_revenue_share_pct']:.2f}% of revenue. Names/actions are provisional."
    ]),
    10: ("Revenue Forecasting and Baselines", [
        f"Scope: {v['forecast_categories']} eligible commodity categories; complete history weeks {v['first_complete_week']}-{v['last_complete_week']}; four direct forecast horizons.",
        "Saved HistGradientBoosting models: validation selects boosting for h1-2 and seasonal naive for h3-4. ARIMA_PLUS is not implemented.",
        f"Frozen test models use labels through {v['evaluation_training_cutoff']}; h1 labels start at {v['training_label_first_week_by_horizon']['1']}. Test targets: {v['test_start']}-{v['test_end']}.",
        f"H1 matched test: boosting MAPE {gb['MAPE_pct']:.2f}% vs naive {naive['MAPE_pct']:.2f}%; RMSE USD {gb['RMSE']:.2f} vs {naive['RMSE']:.2f}.",
        f"Four-week-total WAPE: selected {totals['Validation-selected forecast']['WAPE_pct']:.2f}%, trained-only {totals['Gradient boosting']['WAPE_pct']:.2f}%, seasonal naive {totals['Seasonal naive (52 weeks)']['WAPE_pct']:.2f}%.",
        "Output: weeks 102-105 overlap partial source week 102. Eight-week forecasts and 90% intervals are future assumptions, not implemented results."
    ]),
    11: ("Category Ranking and Proposed Actions", [
        "Index weights: revenue share 25%, growth 15%, reach 20%, repeat 15%, revenue/buyer 15%, promotion association 10% (neutral if unknown).",
        "Highest scored commodities: " + ", ".join(top) + ". These are category priorities, not named consumer SKUs.",
        "Affinity = group category-revenue share / overall share. Forecast and group priorities use separate 60%/40% formulas.",
        "Promote is a provisional measured-test candidate. Every saved execution status requires review; no campaign effect or ROI is estimated.",
        "Assumption for future work: cross-sell under-bought high-scoring categories with a measured comparison group.",
        f"Illustrative assumption: a {top[0]} reactivation coupon after identifying a lapsing subgroup. This action/effect is not implemented or measured."
    ]),
    12: ("Judge and Evidence Guardrails", [
        "Specialists return tool names, structured numbers, scope, definitions and evidence; the app does not run arbitrary SQL.",
        "Judge checks route, source/scope, required numeric claims, fixed summaries and tool-specific consistency.",
        "Failure behavior: rejected answers are withheld. A Supervisor automatic retry loop is not implemented.",
        "Serving requires current processed/model/settings fingerprints and matching independent validation PASS reports.",
        "Short/detail/actions/download content is regenerated from the same checked evidence; unsupported edits are rejected.",
        "Unknown/out-of-scope requests are clarified. SQL bytes-billed caps and cloud-cost limits are not applicable to this local app."
    ]),
    13: ("Approach, Algorithms and Local Tools", [
        "Orchestration: local Python Supervisor, three specialist modules and deterministic Judge; no Google ADK AgentTools.",
        "Chat: supported question patterns and remembered follow-ups; no Gemini, GPT API or external model call.",
        "Data: local CSV sources and validated Parquet tables, using pandas, NumPy and PyArrow.",
        "ML: scikit-learn K-Means and HistGradientBoosting; naive, seasonal-naive and moving-average comparisons; descriptive rankings.",
        "Application: Python Streamlit and Plotly, with concise/detail views, evidence, copy/download and proposed next steps.",
        "Runtime: VS Code F5, project venv, integrated terminal/browser and loopback server. GCP/Docker/cloud deployment are outside current scope."
    ]),
    14: ("Application and Local Runtime", [
        "Chat shows a short answer, detailed explanation and What to do next; checked results have an evidence-validation line.",
        "Expandable transparency shows the selected specialist/tool, scope and deterministic Judge result.",
        "Supporting views show trends, segments, matched forecast errors, four-step revenue outlook and category/recommendation rankings.",
        "Run and preview entirely in VS Code: select FMCG: Local dashboard in VS Code, then press F5. No public deployment.",
        f"Local address (after F5 starts the app): {v['local_url']}. A Cloud Run/public live URL is not applicable."
    ]),
    15: ("Local Demo Walkthrough", [
        "1. How are sales doing? -> Data Science Agent -> query_sales_kpis. Set dataset weeks in the sidebar.",
        f"2. Show customer segments -> Customer/Product Agent -> get_customer_segments. Saved full-window model has {v['chosen_k']} groups.",
        "3. Forecast milk for next month -> Forecast Agent -> forecast_demand. Four dataset weeks, revenue rather than physical units.",
        "4. How can we improve sales? -> Forecast/Recommendation Agent -> get_recommendations. Both priority lists require review.",
        "5. What is the weather in Mumbai? -> clarification/unsupported request; no invented analytics.",
        "Accepted results pass evidence checks. Why?, Give me a short answer and Explain in detail retain the last successful topic."
    ]),
    16: ("Verified Progress and Remaining Evaluation", [
        "Status: the local analytical workflow is ready. A universal 100% completion or production-deployment claim is not supported.",
        "Verified data work",
        "Source inspection, explicit core_consumables_v1 scope and validated processed joins/flags.",
        "EDA, KPIs and week-92 source diagnosis with retained observations.",
        "Verified models and application",
        "Saved RFM/K-Means and four-rule baseline; business labels remain provisional.",
        "Chronological gradient-boosting revenue forecasts with frozen holdout and matched baselines.",
        "Category scores, sensitivity checks and two separate recommendation priority lists.",
        f"Five local roles; {v['verification']['unit_tests_passed']} unit tests, eight dashboard flows and nine natural chat flows passed.",
        "Remaining: human usefulness, temporal robustness, household/decomposition tools and academic Review III evaluation. GCP/deployment excluded."
    ]),
    17: ("Challenges and Learnings", [
        "Unsupported claims: fixed evidence checks and regenerated short/detail text withhold inconsistent answers.",
        "No verified dates/physical units: use dataset weeks and recorded USD revenue; no holiday or unit-demand claim.",
        f"Panel/window handling: analysis begins at week {v['start_week']} by policy; partial week {v['end_week']} stays in KPIs and is excluded from forecast training.",
        "Routing: supported local questions are reproducible; unsupported filters/multiple tasks require clarification.",
        "Runtime: local processed files and loopback serving; cloud accounts, APIs, billing and deployment are not required.",
        "Learning: initialization stability is not temporal stability; baseline wins and recommendation uncertainty must stay visible."
    ]),
    18: ("Conclusion and Future Scope", [
        "Delivered: a local conversational analytics app with checked results, short/detail answers, charts and proposed next steps.",
        "Data science: validated local segmentation, forecasting, category scoring and separate recommendation hypotheses.",
        "Trust: deterministic evidence checks improve consistency; they do not certify causality, business usefulness or every possible user request.",
        "Future assumption: scheduled local refresh of new retailer data after source/scope validation.",
        "Future assumptions: promotion uplift, elasticity, store-level and longer-horizon forecasts with validated intervals.",
        "Future assumptions: proactive alerts and Hindi/Marathi support. These features are not implemented or evaluated."
    ])
    }
    return {number: {"title": title, "paragraphs": paragraphs} for number, (title, paragraphs) in plan.items()}
