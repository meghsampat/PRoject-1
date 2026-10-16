"""Consistency checks for saved direct-horizon evidence consumed by the Judge."""
import math
from numbers import Real
from src import config
from src.forecast_training import metrics


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return isinstance(a, Real) and isinstance(b, Real) and math.isfinite(a) and math.isfinite(b) and math.isclose(a, b, abs_tol=1e-6, rel_tol=1e-9)


def check_metrics(evaluation, rows):
    errors = []
    methods = {**config.FORECAST_METHODS, "Validation-selected forecast": "selected_forecast"}
    if {record["model"] for record in evaluation} != set(methods) or len(evaluation) != len(methods):
        return ["Saved forecast lacks the trained model and all three matched baselines."]
    for record in evaluation:
        calculated = metrics([row["actual_revenue"] for row in rows], [row[methods[record["model"]]] for row in rows])
        if any(not close(value, record.get(name)) for name, value in calculated.items()):
            errors.append("Saved forecast metrics differ from paired holdout evidence.")
    return errors


def validate_saved_forecast(evidence):
    errors = []
    if evidence.get("model_validation_passed") is not True:
        errors.append("Saved forecasting lacks current independent validation.")
    protocol = evidence["evaluation_protocol"]
    start, end, cutoff = protocol["test_start"], protocol["test_end"], protocol["evaluation_training_cutoff"]
    if cutoff != start-1 or end-start+1 != config.FORECAST_HOLDOUT or end != evidence["origin_week"]:
        errors.append("Forecast test/training boundaries are inconsistent.")
    holdout = evidence["holdout"]
    if len(holdout) != sum(config.FORECAST_HOLDOUT-h+1 for h in range(1, config.FORECAST_HORIZON+1)):
        errors.append("Saved holdout pair count is inconsistent.")
    for horizon in range(1, config.FORECAST_HORIZON+1):
        rows = [row for row in holdout if row["horizon"] == horizon]
        if [row["origin_week"] for row in rows] != list(range(cutoff, end-horizon+1)):
            errors.append("Saved forecast origins are not chronological.")
        method = evidence["chosen_methods"][str(horizon)]
        if method not in config.FORECAST_METHODS:
            errors.append("Unknown validation-selected forecast method.")
            continue
        for row in rows:
            if row["target_week"] != row["origin_week"]+horizon or row["target_week"] < start:
                errors.append("Forecast target precedes its stated horizon.")
            if not close(row["selected_forecast"], row[config.FORECAST_METHODS[method]]) or row["selected_method"] != method:
                errors.append("Forecast method disagrees with validation selection.")
        evaluation = [row for row in evidence["evaluation"] if row["horizon"] == horizon]
        errors.extend(check_metrics(evaluation, rows))
    by_origin = {}
    for row in holdout:
        by_origin.setdefault(row["origin_week"], []).append(row)
    complete = {origin: rows for origin, rows in by_origin.items() if len(rows) == config.FORECAST_HORIZON}
    totals = evidence["four_week_totals"]
    if [row["origin_week"] for row in totals] != sorted(complete):
        errors.append("Four-week totals do not match common forecast origins.")
    for row in totals:
        source = complete[row["origin_week"]]
        for name in ["actual_revenue", *config.FORECAST_METHODS.values(), "selected_forecast"]:
            if not close(row[name], sum(part[name] for part in source)):
                errors.append("Four-week total does not reconcile across direct horizons.")
    errors.extend(check_metrics(evidence["four_week_evaluation"], totals))
    for row in evidence["rows"]:
        method = evidence["chosen_methods"][str(row["horizon"])]
        key = "trained_revenue" if method == "Gradient boosting" else config.FORECAST_METHODS[method]
        if row["selected_method"] != method or not close(row["forecast_revenue"], row[key]) or row["forecast_revenue"] < 0:
            errors.append("Served forecast differs from its selected method.")
    return errors
