"""Persist two separate Day 9 evidence rankings from validated processed artifacts."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import pandas as pd
import plotly.express as px
from src import config
from src.artifact_io import file_fingerprint,write_json
from src.category_access import load_category_report
from src.forecast_access import load_forecast_report
from src.segment_access import load_segmentation_report
from src.data_access import load_analysis_transactions,load_validated_aggregate
from src.recommendations import select_target_segments,segment_weekly,category_evidence,rank_candidates,settings_fingerprint
from src.scope import policy_fingerprint


def main():
    config.REC_VALIDATION_FILE.unlink(missing_ok=True)
    load_category_report()
    forecast = load_forecast_report()
    load_segmentation_report()
    if config.REC_RECENT_WEEKS!=config.FORECAST_HORIZON:
        raise ValueError("Recommendation comparison periods must match forecast horizon.")
    window = load_analysis_transactions()
    scores = pd.read_parquet(config.PROCESSED_DIR/"product_scores.parquet")
    future = pd.read_parquet(config.PROCESSED_DIR/"forecast_next_weeks.parquet")
    totals = pd.read_parquet(config.PROCESSED_DIR/"forecast_total_backtest.parquet")
    profiles = pd.read_parquet(config.SEGMENT_PROFILES_FILE)
    assignments = pd.read_parquet(config.HOUSEHOLD_SEGMENTS_FILE)
    affinity = pd.read_parquet(config.PROCESSED_DIR/"segment_product_affinity.parquet")
    weekly = load_validated_aggregate("commodity_weekly")
    weekly = weekly.loc[weekly.in_window]
    origin = forecast["last_complete_week"]
    if origin!=int(weekly.WEEK_NO.max()) or not future.origin_week.eq(origin).all():
        raise ValueError("Forecast origin and weekly evidence differ.")
    for category,g in future.groupby("COMMODITY_DESC"):
        if sorted(g.horizon.tolist())!=list(range(1,config.FORECAST_HORIZON+1)) or not (g.target_week==origin+g.horizon).all():
            raise ValueError("Saved category forecast horizons are incomplete or duplicated.")
    target = select_target_segments(profiles)
    pool_weekly = segment_weekly(window,assignments,target.segment.tolist(),weekly[["COMMODITY_DESC","WEEK_NO"]])
    evidence,target = category_evidence(scores,future,weekly,profiles,affinity,pool_weekly,totals,origin)
    recommendations = rank_candidates(evidence)
    frames = {"recommendations":recommendations,"recommendation_category_evidence":evidence,"recommendation_segment_weekly":pool_weekly}
    for name,frame in frames.items():
        frame.to_parquet(config.PROCESSED_DIR/f"{name}.parquet",index=False,compression=config.PARQUET_COMPRESSION)
    top = recommendations.loc[recommendations.eligible & recommendations["rank"].le(config.REC_DISPLAY_N)]
    top.to_csv(config.OUTPUTS_DIR/"recommendation_top10.csv",index=False)
    figure = px.bar(top,x="recommendation_score",y="COMMODITY_DESC",color="priority_label",facet_col="candidate",
                    orientation="h",hover_data=["forecast_growth","target_affinity","target_recent_momentum","promotion_evidence_status"],
                    title="Separate recommendation hypotheses; scores compare within each method")
    figure.update_yaxes(matches=None)
    figure.write_html(config.OUTPUTS_DIR/"recommendation_diagnostics.html",include_plotlyjs=True)
    top_sets = {method:set(top.loc[top.candidate.eq(method),"COMMODITY_DESC"]) for method in config.REC_METHODS}
    shared = sorted(top_sets["forecast"] & top_sets["segment"])
    paths = [config.PROCESSED_DIR/f"{name}.parquet" for name in config.REC_TABLES]
    paths += [config.OUTPUTS_DIR/name for name in config.REC_OUTPUT_NAMES]
    write_json(config.REC_BUILD_FILE,{
        "status":"BUILT_REQUIRES_VALIDATION","policy_fingerprint":policy_fingerprint(),
        "settings_fingerprint":settings_fingerprint(),"master_sha256":file_fingerprint(config.MASTER_FILE)["sha256"],
        "upstream_builds":{name:file_fingerprint(path)["sha256"] for name,path in config.REC_UPSTREAM_BUILDS.items()},
        "upstream_validations":{name:file_fingerprint(path)["sha256"] for name,path in config.REC_UPSTREAM_VALIDATIONS.items()},
        "start_week":int(window.WEEK_NO.min()),"end_week":int(window.WEEK_NO.max()),"origin_week":origin,
        "as_of_week":int(window.WEEK_NO.max()),"as_of_day":int(window.DAY.max()),"partial_forecast_overlap":[w for w in forecast["excluded_partial_weeks"] if origin < w <= origin+config.FORECAST_HORIZON],"forecast_weeks":list(range(origin+1,origin+config.FORECAST_HORIZON+1)),
        "recent_weeks":list(range(origin-config.REC_RECENT_WEEKS+1,origin+1)),
        "previous_weeks":list(range(origin-2*config.REC_RECENT_WEEKS+1,origin-config.REC_RECENT_WEEKS+1)),
        "transaction_lines":len(window),"households":int(window.household_key.nunique()),"revenue":float(window.SALES_VALUE.sum()),
        "scored_category_cohort":len(evidence),"candidate_rows":len(recommendations),
        "eligible_counts":{method:int(recommendations.loc[recommendations.candidate.eq(method),"eligible"].sum()) for method in config.REC_METHODS},
        "weights":{"forecast":config.REC_FORECAST_WEIGHTS,"segment":config.REC_SEGMENT_WEIGHTS},
        "target_segments":target[["segment","segment_name","households","revenue","revenue_share_pct","revenue_per_week_median_index"]].to_dict("records"),
        "target_households":int(target.households.sum()),"target_revenue_share_pct":float(target.revenue_share_pct.sum()),
        "top10_shared_categories":shared,"top10_overlap_count":len(shared),
        "priority_counts":{method:recommendations.loc[recommendations.candidate.eq(method)].priority_label.value_counts().to_dict() for method in config.REC_METHODS},
        "available_promotion_associations":int(evidence.promotion_evidence_available.sum()),
        "business_usefulness_review_complete":False,"arbitration_implemented":False,
        "note":"Analyst heuristics, separate evidence lists, no ground-truth recommendation accuracy. Promote means candidate for a measured test; all execution statuses require review. Forecast revenue is organic outlook, not incremental promotion lift. Missing promotion associations remain unknown. Affinity is observed revenue mix, not causal response or lifetime value. Rank-normalized affinity can amplify small absolute differences. Scores are only comparable within each method. No merged list, automatic winner, campaign execution or invented ROI.",
        "artifacts":[file_fingerprint(path) for path in paths]})
    print("Recommendation counts:",{method:int(recommendations.loc[recommendations.candidate.eq(method),"eligible"].sum()) for method in config.REC_METHODS},flush=True)
    print(top[["candidate","rank","COMMODITY_DESC","recommendation_score","priority_label"]].to_string(index=False),flush=True)
    print(f"Top-10 overlap: {len(shared)}. Run src/validate_recommendations.py.",flush=True)


if __name__=="__main__":
    main()
