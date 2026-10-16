"""Deterministic evidence checks, not an LLM quality scorer or independent data audit."""
import math
from numbers import Real
from src.answer_templates import render_answer
from src.config import FORECAST_HOLDOUT
from src import config
from src.supervisor import ROUTES
from src.tools import forecast_metrics

EXPECTED_CLAIMS = {
    "query_sales_kpis": {"revenue", "baskets", "households", "average_basket_value"},
    "get_sales_trend": {"revenue"},
    "get_week_diagnosis": {"revenue", "reference_revenue", "revenue_change_pct"},
    "get_product_performance": {"products_shown"},
    "get_customer_segments": {"chosen_k", "silhouette", "households"},
    "get_category_intelligence": {"categories_shown", "categories_scored", "top_score"},
    "forecast_demand": {"forecast_total", "forecast_horizon", "origin_week"},
    "get_recommendations": {"forecast_candidates_shown", "segment_candidates_shown", "top10_overlap_count"},
}


def close(left, right):
    return isinstance(left, Real) and isinstance(right, Real) and not isinstance(left, bool) and not isinstance(right, bool) and math.isfinite(left) and math.isfinite(right) and math.isclose(left, right, rel_tol=1e-9, abs_tol=1e-6)


def judge_result(errors):
    return {"accepted": not errors, "status": "PASS" if not errors else "REJECTED",
            "errors": errors, "checks": ["Route matches specialist/tool", "Source, scope, and currency", "Numeric claims and answer text match evidence", "Tool-specific consistency"],
            "method": "Deterministic schema and consistency Judge",
            "limitation": "Does not certify raw-data provenance, independently recompute all tools, or score business value. Answers use fixed templates; free-form LLM text is not supported.",
            "retry_status": "No automatic retry; rejected answers are withheld"}


def validate_answer(response, decision, start_week, end_week):
    errors = []
    if not isinstance(response, dict) or not isinstance(decision, dict):
        return judge_result(["Response and decision must be structured dictionaries."])
    evidence = response.get("evidence", {})
    claims = response.get("claims", {})
    if not isinstance(evidence, dict) or not isinstance(claims, dict):
        return judge_result(["Claims and evidence must be structured dictionaries."])
    tool = response.get("tool")
    expected_route = ROUTES.get(decision.get("intent"))
    if expected_route != (response.get("specialist"), tool):
        errors.append("Specialist/tool does not match the Supervisor route.")
    for field in ["scope", "source_table", "revenue_definition", "result_status"]:
        if not isinstance(evidence.get(field), str) or not evidence[field]:
            errors.append(f"Evidence is missing {field}.")
    expected_source = "transactions_master.parquet" if tool in {"query_sales_kpis", "get_sales_trend", "get_customer_segments"} else "transactions_master.parquet + product_lookup.parquet"
    if tool == "get_customer_segments" and evidence.get("mode") == "saved_model":
        expected_source = config.SEGMENT_MODEL_SOURCE
        if evidence.get("model_validation_passed") is not True or not isinstance(evidence.get("stability_mean_ari"), Real) or evidence["stability_mean_ari"] < config.MIN_STABILITY_MEAN_ARI:
            errors.append("Saved segmentation lacks validated stability evidence.")
    if tool == "get_category_intelligence":
        expected_source = config.CATEGORY_MODEL_SOURCE
        if evidence.get("scoring_validation_passed") is not True:
            errors.append("Category scores lack current validation evidence.")
    if tool == "forecast_demand" and evidence.get("mode") == "saved_direct_model":
        expected_source = config.FORECAST_MODEL_SOURCE
    if tool == "get_recommendations":
        expected_source = config.REC_MODEL_SOURCE
    if tool == "get_week_diagnosis":
        expected_source = config.DIAG_MODEL_SOURCE
    if evidence.get("source_table") != expected_source:
        errors.append("Source does not match the selected tool.")
    if evidence.get("start_week") != start_week or evidence.get("end_week") != end_week or evidence.get("currency") != "USD":
        errors.append("Evidence scope or currency is inconsistent with the request.")
    if tool not in EXPECTED_CLAIMS or set(claims) != EXPECTED_CLAIMS.get(tool):
        errors.append("Required numeric claims are missing or unexpected.")
    for field, value in claims.items():
        if not close(value, evidence.get(field)):
            errors.append(f"Unsupported numeric claim: {field}.")
    try:
        # This equality prevents adding unsupported numbers or assertions to a fixed-template answer.
        if response.get("answer") != render_answer(tool, evidence):
            errors.append("Business answer differs from its evidence-derived template.")
        if tool == "query_sales_kpis":
            if evidence["baskets"] <= 0 or not close(evidence["average_basket_value"], evidence["revenue"] / evidence["baskets"]):
                errors.append("Average basket value is inconsistent.")
        elif tool == "get_sales_trend":
            if not close(sum(row["revenue"] for row in evidence["rows"]), evidence["revenue"]):
                errors.append("Weekly revenue does not reconcile.")
        elif tool == "get_week_diagnosis":
            if evidence.get("validation_passed") is not True or evidence.get("cause_verified") is not False or evidence["week"] != config.DIAG_TARGET_WEEK:
                errors.append("Week diagnosis lacks current validation or makes an unsupported cause claim.")
            references = [w for w in range(config.DIAG_TARGET_WEEK-config.DIAG_NEIGHBOR_RADIUS,config.DIAG_TARGET_WEEK+config.DIAG_NEIGHBOR_RADIUS+1) if w != config.DIAG_TARGET_WEEK]
            if evidence["reference_weeks"] != references:
                errors.append("Week diagnostic reference periods are inconsistent.")
            target = [row for row in evidence["rows"] if row["WEEK_NO"]==evidence["week"]]
            baseline = [row for row in evidence["rows"] if row["WEEK_NO"] in references]
            if len(target)!=1 or len(baseline)!=len(references) or len({row["WEEK_NO"] for row in evidence["rows"]})!=len(evidence["rows"]):
                errors.append("Week diagnostic weekly evidence is incomplete.")
            else:
                mean=sum(row["revenue"] for row in baseline)/len(references)
                if not close(target[0]["revenue"],evidence["revenue"]) or not close(mean,evidence["reference_revenue"]) or not close((target[0]["revenue"]/mean-1)*100,evidence["revenue_change_pct"]):
                    errors.append("Week diagnostic revenue/change does not reconcile.")
                departments=evidence["department_rows"]
                if not close(sum(row["target_revenue"] for row in departments),evidence["revenue"]) or not close(sum(row["reference_mean_revenue"] for row in departments),mean):
                    errors.append("Department contributions do not reconcile.")
            breadth=evidence["breadth"]
            broad=(breadth["positive_major_departments"]>=config.DIAG_MIN_POSITIVE_DEPTS
                   and breadth["positive_store_fraction"]>=config.DIAG_MIN_POSITIVE_STORE_FRACTION
                   and breadth["positive_department_baseline_share"]>=config.DIAG_MIN_POSITIVE_DEPT_BASELINE_SHARE
                   and breadth["top_store_positive_delta_share"]<=config.DIAG_MAX_TOP_STORE_DELTA_SHARE)
            if breadth["broad_pattern"] != broad:
                errors.append("Diagnostic breadth label does not match its evidence.")
        elif tool == "get_product_performance":
            rows = evidence["rows"]
            if len(rows) != evidence["products_shown"] or any(a["revenue"] < b["revenue"] for a, b in zip(rows, rows[1:])):
                errors.append("Product ranking is inconsistent.")
        elif tool == "get_category_intelligence":
            rows = evidence["rows"]
            weights = evidence["weights"]
            if weights != config.CATEGORY_WEIGHTS or not close(sum(weights.values()), 1):
                errors.append("Category weights differ from documented policy.")
            if not rows or len(rows) != evidence["categories_shown"] or evidence["categories_scored"] != config.CATEGORY_TOP_N or len(rows) > evidence["categories_scored"]:
                errors.append("Category cohort/counts are inconsistent.")
            if len({row["COMMODITY_DESC"] for row in rows}) != len(rows) or [row["rank"] for row in rows] != list(range(1, len(rows)+1)):
                errors.append("Category ranks/identities are inconsistent.")
            for row in rows:
                values = [row["normalized_" + name] for name in weights]
                if any(not isinstance(value, Real) or not math.isfinite(value) or not 0 <= value <= 1 for value in values):
                    errors.append("Invalid normalized category component.")
                calculated = sum(row["normalized_" + name] * weight for name, weight in weights.items()) * config.CATEGORY_SCORE_SCALE
                if not close(row["score"], calculated):
                    errors.append("Category composite score does not match its components.")
            if not close(evidence["top_score"], rows[0]["score"]) or any(a["score"] < b["score"] for a, b in zip(rows, rows[1:])):
                errors.append("Category score ordering is inconsistent.")
        elif tool == "get_customer_segments":
            rows = evidence["rows"]
            if sum(row["households"] for row in rows) != evidence["households"] or len(rows) != evidence["chosen_k"]:
                errors.append("Segment sizes do not reconcile.")
            if not close(sum(row["revenue"] for row in rows), evidence["revenue"]):
                errors.append("Segment revenue does not reconcile.")
            selected = [row for row in evidence["evaluation"] if row["k"] == evidence["chosen_k"] and row["eligible"]]
            eligible = [row for row in evidence["evaluation"] if row["eligible"]]
            if len(selected) != 1 or not close(selected[0]["silhouette"], evidence["silhouette"]) or evidence["silhouette"] < max(row["silhouette"] for row in eligible):
                errors.append("Chosen clustering score lacks consistent evaluation evidence.")
        elif tool == "get_recommendations":
            from src.recommendation_evidence import validate_recommendation_evidence
            errors.extend(validate_recommendation_evidence(evidence))
        elif tool == "forecast_demand":
            rows = evidence["rows"]
            if not rows or len(rows) != evidence["forecast_horizon"] or not close(sum(row["forecast_revenue"] for row in rows), evidence["forecast_total"]):
                errors.append("Forecast total or horizon is inconsistent.")
            if [row["week"] for row in rows] != list(range(evidence["origin_week"] + 1, evidence["origin_week"] + 1 + len(rows))):
                errors.append("Forecast weeks are inconsistent with the origin.")
            if evidence.get("mode") == "saved_direct_model":
                from src.forecast_evidence import validate_saved_forecast
                errors.extend(validate_saved_forecast(evidence))
            else:
                if not {"Naive", "Four-week moving average"}.issubset({row["model"] for row in evidence["evaluation"]}):
                    errors.append("Forecast lacks baseline comparison evidence.")
                holdout = evidence["holdout"]
                if len(holdout) != FORECAST_HOLDOUT or [row["week"] for row in holdout] != list(range(evidence["origin_week"] - FORECAST_HOLDOUT + 1, evidence["origin_week"] + 1)):
                    errors.append("Holdout weeks do not match the last complete forecast history.")
                model_columns = {"Naive": "naive", "Four-week moving average": "moving_average", "Seasonal naive (52 weeks)": "seasonal_naive"}
                for evaluation in evidence["evaluation"]:
                    predicted = [row[model_columns[evaluation["model"]]] for row in holdout]
                    recomputed = forecast_metrics([row["actual_revenue"] for row in holdout], predicted)
                    for metric, value in recomputed.items():
                        reported = evaluation.get(metric)
                        if (value is None and reported is not None) or (value is not None and not close(value, reported)):
                            errors.append(f"Forecast metric lacks matching holdout evidence: {evaluation['model']} {metric}.")
    except (KeyError, TypeError, ZeroDivisionError, ValueError, OverflowError):
        errors.append("Tool evidence has an invalid structure.")
    return judge_result(errors)






