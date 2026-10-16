"""Build Day 6 category intelligence from approved, validated processed sources."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
import plotly.express as px
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.category_access import load_promotion_report
from src.category_scoring import category_indicators, score_categories, settings_fingerprint, weight_sensitivity
from src.data_access import load_analysis_transactions, load_validated_aggregate
from src.promotion_support import promotion_diagnostics
from src.scope import policy_fingerprint


def main():
    config.CATEGORY_VALIDATION_FILE.unlink(missing_ok=True)
    promotion = load_promotion_report()
    window = load_analysis_transactions()
    weekly = load_validated_aggregate("commodity_weekly")
    weekly = weekly.loc[weekly.in_window].copy()
    daily = load_validated_aggregate("commodity_daily")
    daily = daily.loc[daily.in_window].copy()
    exposure = pd.read_parquet(config.PROCESSED_DIR / "promo_category_weekly.parquet")
    components = category_indicators(window, weekly, daily)
    promo = promotion_diagnostics(weekly, exposure)
    components = components.merge(promo, on="COMMODITY_DESC", validate="one_to_one")
    scores = score_categories(components)
    sensitivity, ranges = weight_sensitivity(scores)
    scores = scores.merge(ranges.drop(columns="base_rank"), on="COMMODITY_DESC", validate="one_to_one")
    for name, frame in [("category_components", components), ("product_scores", scores), ("promo_lift", promo)]:
        frame.to_parquet(config.PROCESSED_DIR / f"{name}.parquet", index=False, compression=config.PARQUET_COMPRESSION)
    sensitivity.to_csv(config.OUTPUTS_DIR / "category_weight_sensitivity.csv", index=False)
    ranges.to_csv(config.OUTPUTS_DIR / "category_rank_ranges.csv", index=False)
    top = scores.head(config.CATEGORY_DISPLAY_N).sort_values("score")
    figure = px.bar(top, x="score", y="COMMODITY_DESC", orientation="h",
                    hover_data=["rank", "minimum_rank", "maximum_rank", "growth", "yoy_growth", "promotion_reason"],
                    title="Category intelligence: descriptive score and sensitivity rank range")
    figure.update_layout(xaxis_title="Analyst-weighted percentile index (0-100)", yaxis_title="Commodity", height=800)
    figure.write_html(config.OUTPUTS_DIR / "category_diagnostics.html", include_plotlyjs=True)
    stats = {"runs": len(sensitivity), "relative_weight_perturbation": config.CATEGORY_WEIGHT_PERTURBATION,
             "spearman_all_min": float(sensitivity.spearman_all.min()),
             "spearman_all_median": float(sensitivity.spearman_all.median()),
             "spearman_baseline_top20_min": float(sensitivity.spearman_baseline_top20.min()),
             "spearman_baseline_top20_median": float(sensitivity.spearman_baseline_top20.median()),
             "top20_overlap_min": float(sensitivity.top20_overlap_share.min()),
             "top20_overlap_median": float(sensitivity.top20_overlap_share.median())}
    stats["engineering_stability_gate_passed"] = bool(stats["spearman_all_min"] >= config.CATEGORY_MIN_SPEARMAN and stats["top20_overlap_min"] >= config.CATEGORY_MIN_TOP20_OVERLAP)
    paths = [config.PROCESSED_DIR / f"{name}.parquet" for name in config.CATEGORY_TABLES]
    paths += [config.OUTPUTS_DIR / name for name in config.CATEGORY_OUTPUT_NAMES]
    write_json(config.CATEGORY_BUILD_FILE, {
        "status": "BUILT_REQUIRES_VALIDATION", "policy_fingerprint": policy_fingerprint(),
        "settings_fingerprint": settings_fingerprint(), "master_sha256": file_fingerprint(config.MASTER_FILE)["sha256"],
        "sources": {name: file_fingerprint(config.PROCESSED_DIR / f"{name}.parquet")["sha256"] for name in ["commodity_daily", "commodity_weekly"]},
        "promotion_build_sha256": file_fingerprint(config.PROMOTION_BUILD_FILE)["sha256"],
        "start_week": int(window.WEEK_NO.min()), "end_week": int(window.WEEK_NO.max()),
        "first_complete_week": int(weekly.WEEK_NO.min()), "last_complete_week": int(weekly.WEEK_NO.max()),
        "complete_weeks": int(weekly.WEEK_NO.nunique()), "first_half_weeks": int(weekly.WEEK_NO.nunique() // 2),
        "second_half_weeks": int(weekly.WEEK_NO.nunique() - weekly.WEEK_NO.nunique() // 2),
        "transaction_lines": len(window), "households": int(window.household_key.nunique()),
        "revenue": float(window.SALES_VALUE.sum()), "all_categories": len(components), "scored_categories": len(scores),
        "weights": config.CATEGORY_WEIGHTS, "sensitivity": stats,
        "promotion_coverage_share": promotion["coverage_share"],
        "scored_eligible_promotion_associations": int(scores.promotion_association.notna().sum()),
        "scored_eligible_any_vs_none_comparisons": int(scores.any_promo_association_shrunk.notna().sum()),
        "top10": scores.head(10)[["COMMODITY_DESC", "score", "rank"]].to_dict("records"),
        "business_usefulness_review_complete": False,
        "note": "Analyst weights prioritize sales reach/scale (45%), retention/value (30%), recent growth (15%), guarded promotion association (10%). Correlated components are deliberate and not independent evidence. Promotion term uses higher-versus-lower matched exposure; with-versus-without diagnostics are saved separately and may be unestimable. Missing components normalized to 0.5, not recorded as zero association. Scope and calendar limitations remain.",
        "artifacts": [file_fingerprint(path) for path in paths]})
    print(f"Built {len(scores)} category scores from {len(components)} categories. Sensitivity: {stats}", flush=True)
    print(scores.head(10)[["COMMODITY_DESC", "score", "rank"]].to_string(index=False), flush=True)
    print("Run src/validate_product_scores.py before serving results.", flush=True)


if __name__ == "__main__":
    main()
