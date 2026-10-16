"""Two descriptive recommendation hypotheses with separate, documented evidence."""
import hashlib
import json
import numpy as np
import pandas as pd
from src import config
from src.forecast_training import metrics


def settings_fingerprint():
    names = ["REC_RECENT_WEEKS", "REC_DISPLAY_N", "REC_HIGH_SPEND_INDEX", "REC_MIN_TARGET_BUYERS",
             "REC_FORECAST_WEIGHTS", "REC_SEGMENT_WEIGHTS", "REC_PROMOTE_GROWTH", "REC_REVIEW_DECLINE",
             "REC_PROMOTE_AFFINITY", "REC_MAX_FORECAST_WAPE", "REC_NEUTRAL_RANK", "REC_SCORE_SCALE",
             "FORECAST_HORIZON", "CURRENCY"]
    return hashlib.sha256(json.dumps({name:getattr(config,name) for name in names},sort_keys=True).encode()).hexdigest()


def select_target_segments(profiles):
    selected = profiles.loc[profiles.revenue_per_week_median_index.ge(config.REC_HIGH_SPEND_INDEX)].copy()
    if selected.empty:
        raise ValueError("No segment meets the documented observed-spending rule; do not force a target.")
    return selected.sort_values("segment")


def safe_growth(after, before):
    return after / before.where(before.gt(0)) - 1


def normalize_eligible(values):
    if values.isna().any() or not np.isfinite(values.to_numpy()).all():
        raise ValueError("Ranking requires finite eligible evidence.")
    if len(values)<2 or values.nunique()<2:
        return pd.Series(config.REC_NEUTRAL_RANK,index=values.index,dtype=float)
    return (values.rank(method="average")-1)/(len(values)-1)


def combine(normalized, weights):
    if set(normalized)!=set(weights) or any(not np.isfinite(weight) or weight<0 for weight in weights.values()) or not np.isclose(sum(weights.values()),1):
        raise ValueError("Recommendation weights must be finite, nonnegative and sum to one.")
    if normalized.isna().any().any() or not normalized.ge(0).all().all() or not normalized.le(1).all().all():
        raise ValueError("Recommendation components must be finite and normalized to [0,1].")
    return normalized.mul(pd.Series(weights)).sum(axis=1)*config.REC_SCORE_SCALE


def segment_weekly(window, assignments, target_ids, weekly_grid):
    members = assignments.loc[assignments.segment.isin(target_ids),"household_key"]
    complete = window.loc[window.IS_COMPLETE_WEEK & window.household_key.isin(members)]
    totals = complete.groupby(["COMMODITY_DESC","WEEK_NO"]).agg(
        segment_revenue=("SALES_VALUE","sum"),segment_buyers=("household_key","nunique"))
    return weekly_grid.merge(totals.reset_index(),on=["COMMODITY_DESC","WEEK_NO"],how="left",validate="one_to_one").fillna({"segment_revenue":0,"segment_buyers":0})


def category_evidence(scores, future, weekly, profiles, affinity, pool_weekly, total_backtest, origin):
    target = select_target_segments(profiles)
    target_ids = target.segment.tolist()
    size = config.REC_RECENT_WEEKS
    recent = weekly.loc[weekly.WEEK_NO.between(origin-size+1,origin)].groupby("COMMODITY_DESC").revenue.sum()
    previous = weekly.loc[weekly.WEEK_NO.between(origin-2*size+1,origin-size)].groupby("COMMODITY_DESC").revenue.sum()
    predictions = future.groupby("COMMODITY_DESC").selected_forecast.sum()
    steps = future.groupby("COMMODITY_DESC").horizon.nunique()
    evidence = scores[["COMMODITY_DESC","score","promotion_association","promotion_reason"]].rename(columns={"score":"product_score"}).copy()
    evidence["trailing_four_week_revenue"] = evidence.COMMODITY_DESC.map(recent)
    evidence["previous_four_week_revenue"] = evidence.COMMODITY_DESC.map(previous)
    evidence["forecast_four_week_revenue"] = evidence.COMMODITY_DESC.map(predictions)
    evidence["forecast_available"] = evidence.COMMODITY_DESC.map(steps).eq(config.FORECAST_HORIZON)
    evidence["forecast_growth"] = safe_growth(evidence.forecast_four_week_revenue,evidence.trailing_four_week_revenue)
    evidence["overall_recent_momentum"] = safe_growth(evidence.trailing_four_week_revenue,evidence.previous_four_week_revenue)
    selected = affinity.loc[affinity.segment.isin(target_ids)].copy()
    category_pool = selected.groupby("COMMODITY_DESC").agg(target_category_revenue=("revenue","sum"),target_buyers=("buyers","sum"))
    # Segments partition households: distinct buyer counts can be added across disjoint segments.
    pool_total = float(target.revenue.sum())
    overall_share = selected.groupby("COMMODITY_DESC").overall_category_share.first()
    category_pool["target_affinity"] = (category_pool.target_category_revenue/pool_total)/overall_share.replace(0,np.nan)
    evidence = evidence.merge(category_pool.reset_index(),on="COMMODITY_DESC",how="left",validate="one_to_one")
    pr = pool_weekly.loc[pool_weekly.WEEK_NO.between(origin-size+1,origin)].groupby("COMMODITY_DESC").segment_revenue.sum()
    pp = pool_weekly.loc[pool_weekly.WEEK_NO.between(origin-2*size+1,origin-size)].groupby("COMMODITY_DESC").segment_revenue.sum()
    evidence["target_recent_revenue"] = evidence.COMMODITY_DESC.map(pr)
    evidence["target_previous_revenue"] = evidence.COMMODITY_DESC.map(pp)
    evidence["target_recent_momentum"] = safe_growth(evidence.target_recent_revenue,evidence.target_previous_revenue)
    quality = []
    for category,g in total_backtest.groupby("COMMODITY_DESC"):
        learned = metrics(g.actual_revenue,g.selected_forecast)["WAPE_pct"]
        baselines = {name:metrics(g.actual_revenue,g[column])["WAPE_pct"] for name,column in config.FORECAST_METHODS.items() if name!="Gradient boosting"}
        valid = {name:value for name,value in baselines.items() if value is not None}
        best = min(valid,key=lambda name:(valid[name],name)) if valid else None
        quality.append({"COMMODITY_DESC":category,"forecast_total_WAPE_pct":learned,
                        "best_baseline_total_WAPE_pct":valid[best] if best else np.nan,
                        "best_baseline":best,"forecast_total_backtest_origins":len(g)})
    evidence = evidence.merge(pd.DataFrame(quality),on="COMMODITY_DESC",how="left",validate="one_to_one")
    evidence["promotion_evidence_available"] = evidence.promotion_association.notna()
    return evidence, target


def priority_label(method,row):
    if not row.eligible:
        return "review"
    growth = row.forecast_growth if method=="forecast" else row.target_recent_momentum
    if growth < -config.REC_REVIEW_DECLINE:
        return "review"
    if method=="forecast" and (pd.isna(row.forecast_total_WAPE_pct) or row.forecast_total_WAPE_pct>config.REC_MAX_FORECAST_WAPE):
        return "review"
    qualifies = method=="forecast" or row.target_affinity>=config.REC_PROMOTE_AFFINITY
    return "promote" if row.rank<=config.REC_DISPLAY_N and growth>=config.REC_PROMOTE_GROWTH and qualifies else "maintain"


def rank_candidates(evidence):
    records = []
    for method,weights in [("forecast",config.REC_FORECAST_WEIGHTS),("segment",config.REC_SEGMENT_WEIGHTS)]:
        frame = evidence.copy()
        frame["candidate"] = method
        if method=="forecast":
            frame["eligible"] = frame.forecast_available & frame.forecast_growth.notna() & np.isfinite(frame.forecast_growth) & frame.product_score.between(0,100)
            frame["eligibility_reason"] = np.where(frame.eligible,"eligible","forecast unavailable or invalid trailing revenue")
        else:
            frame["eligible"] = frame.target_affinity.notna() & frame.target_recent_momentum.notna() & np.isfinite(frame.target_affinity) & np.isfinite(frame.target_recent_momentum) & frame.target_buyers.ge(config.REC_MIN_TARGET_BUYERS)
            frame["eligibility_reason"] = np.where(frame.eligible,"eligible","insufficient target buyers or undefined affinity/momentum")
        chosen = frame.loc[frame.eligible]
        if chosen.empty:
            raise ValueError(f"No eligible {method} recommendation candidates.")
        frame["component_primary"] = np.nan
        frame["component_secondary"] = np.nan
        frame["recommendation_score"] = np.nan
        if method=="forecast":
            components = pd.DataFrame({"forecast_growth":normalize_eligible(chosen.forecast_growth),"product_score":chosen.product_score/config.CATEGORY_SCORE_SCALE})
        else:
            components = pd.DataFrame({"target_affinity":normalize_eligible(chosen.target_affinity),"target_momentum":normalize_eligible(chosen.target_recent_momentum)})
        frame.loc[chosen.index,"component_primary"] = components.iloc[:,0]
        frame.loc[chosen.index,"component_secondary"] = components.iloc[:,1]
        frame.loc[chosen.index,"recommendation_score"] = combine(components,weights)
        order = frame.loc[frame.eligible].sort_values(["recommendation_score","COMMODITY_DESC"],ascending=[False,True])
        frame["rank"] = pd.Series(pd.NA,index=frame.index,dtype="Int64")
        frame.loc[order.index,"rank"] = np.arange(1,len(order)+1)
        frame["priority_label"] = [priority_label(method,row) for row in frame.itertuples()]
        frame["execution_status"] = "review_required"
        frame["promotion_evidence_status"] = np.where(frame.promotion_evidence_available,"observational association","unavailable")
        frame["reason"] = np.where(~frame.eligible,frame.eligibility_reason,
            ("Forecast growth and category score prioritize a test hypothesis; inspect forecast error versus baseline."
             if method=="forecast" else "Observed spending-group affinity and recent group momentum prioritize a test hypothesis."))
        records.append(frame.sort_values(["rank","COMMODITY_DESC"],na_position="last"))
    return pd.concat(records,ignore_index=True)
