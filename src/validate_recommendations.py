"""Independent Day 9 source arithmetic, pooling, rankings, labels and overlap checks."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint,write_json
from src.data_access import load_analysis_transactions,load_validated_aggregate
from src.recommendation_access import load_recommendation_report


def ratio(after,before):
    return after/before-1 if before>0 else np.nan


def direct_wape(group,column):
    denominator=np.abs(group.actual_revenue).sum()
    return float(np.abs(group.actual_revenue-group[column]).sum()/denominator*100) if denominator else np.nan


def main():
    report=load_recommendation_report(require_validation=False)
    window=load_analysis_transactions()
    weekly=load_validated_aggregate("commodity_weekly")
    weekly=weekly.loc[weekly.in_window]
    scores=pd.read_parquet(config.PROCESSED_DIR/"product_scores.parquet").set_index("COMMODITY_DESC")
    future=pd.read_parquet(config.PROCESSED_DIR/"forecast_next_weeks.parquet")
    totals=pd.read_parquet(config.PROCESSED_DIR/"forecast_total_backtest.parquet")
    profiles=pd.read_parquet(config.SEGMENT_PROFILES_FILE)
    assignments=pd.read_parquet(config.HOUSEHOLD_SEGMENTS_FILE)
    evidence=pd.read_parquet(config.PROCESSED_DIR/"recommendation_category_evidence.parquet").set_index("COMMODITY_DESC")
    table=pd.read_parquet(config.PROCESSED_DIR/"recommendations.parquet")
    pool_weekly=pd.read_parquet(config.PROCESSED_DIR/"recommendation_segment_weekly.parquet")
    assert evidence.index.is_unique and set(evidence.index)==set(scores.index)
    assert not table.duplicated(["candidate","COMMODITY_DESC"]).any()
    assert len(table)==len(scores)*len(config.REC_METHODS)
    assert report["scored_category_cohort"]==len(scores) and report["candidate_rows"]==len(table)
    assert report["as_of_week"]==int(window.WEEK_NO.max()) and report["as_of_day"]==int(window.DAY.max())
    assert report["revenue"]==float(window.SALES_VALUE.sum()) and report["transaction_lines"]==len(window)
    origin=int(weekly.WEEK_NO.max())
    size=config.REC_RECENT_WEEKS
    recent=list(range(origin-size+1,origin+1)); previous=list(range(origin-2*size+1,origin-size+1))
    assert report["origin_week"]==origin and report["recent_weeks"]==recent and report["previous_weeks"]==previous
    assert report["forecast_weeks"]==list(range(origin+1,origin+config.FORECAST_HORIZON+1))
    partial=sorted(set(window.WEEK_NO)-set(weekly.WEEK_NO))
    assert report["partial_forecast_overlap"]==[week for week in partial if week in report["forecast_weeks"]]
    target=profiles.loc[profiles.revenue_per_week_median_index.ge(config.REC_HIGH_SPEND_INDEX)].sort_values("segment")
    assert not target.empty
    assert target.segment.tolist()==[row["segment"] for row in report["target_segments"]]
    members=assignments.loc[assignments.segment.isin(target.segment),"household_key"]
    assert members.is_unique and len(members)==report["target_households"]==target.households.sum()
    pool=window.loc[window.household_key.isin(members)]
    assert np.isclose(pool.SALES_VALUE.sum(),target.revenue.sum())
    assert np.isclose(report["target_revenue_share_pct"],pool.SALES_VALUE.sum()/window.SALES_VALUE.sum()*100)
    direct_pool=pool.loc[pool.IS_COMPLETE_WEEK].groupby(["COMMODITY_DESC","WEEK_NO"]).agg(segment_revenue=("SALES_VALUE","sum"),segment_buyers=("household_key","nunique"))
    expected=weekly[["COMMODITY_DESC","WEEK_NO"]].merge(direct_pool.reset_index(),how="left",on=["COMMODITY_DESC","WEEK_NO"],validate="one_to_one").fillna({"segment_revenue":0,"segment_buyers":0})
    pd.testing.assert_frame_equal(pool_weekly,expected,check_dtype=False)
    pool_revenue=pool.groupby("COMMODITY_DESC").SALES_VALUE.sum()
    pool_buyers=pool.groupby("COMMODITY_DESC").household_key.nunique()
    overall_revenue=window.groupby("COMMODITY_DESC").SALES_VALUE.sum()
    checks=[]
    for category,row in evidence.iterrows():
        assert np.isclose(row.product_score,scores.loc[category,"score"])
        assert np.isclose(row.promotion_association,scores.loc[category,"promotion_association"],equal_nan=True)
        assert row.promotion_reason==scores.loc[category,"promotion_reason"]
        g=weekly.loc[weekly.COMMODITY_DESC.eq(category)]
        trailing=float(g.loc[g.WEEK_NO.isin(recent),"revenue"].sum())
        prior=float(g.loc[g.WEEK_NO.isin(previous),"revenue"].sum())
        predicted=future.loc[future.COMMODITY_DESC.eq(category)]
        if len(predicted):
            assert sorted(predicted.horizon)==list(range(1,config.FORECAST_HORIZON+1))
            assert np.array_equal(predicted.target_week,predicted.origin_week+predicted.horizon)
            assert predicted.origin_week.eq(origin).all()
            forecast=float(predicted.selected_forecast.sum())
        else:
            forecast=np.nan
        assert row.forecast_available==(len(predicted)==config.FORECAST_HORIZON)
        assert np.isclose(row.trailing_four_week_revenue,trailing) and np.isclose(row.previous_four_week_revenue,prior)
        assert np.isclose(row.forecast_four_week_revenue,forecast,equal_nan=True)
        assert np.isclose(row.forecast_growth,ratio(forecast,trailing),equal_nan=True)
        assert np.isclose(row.overall_recent_momentum,ratio(trailing,prior),equal_nan=True)
        cat_pool=float(pool_revenue.get(category,0))
        cat_buyers=int(pool_buyers.get(category,0))
        affinity=(cat_pool/pool.SALES_VALUE.sum())/(overall_revenue.loc[category]/window.SALES_VALUE.sum())
        assert np.isclose(row.target_category_revenue,cat_pool) and row.target_buyers==cat_buyers
        assert np.isclose(row.target_affinity,affinity)
        category_pool=pool.loc[pool.COMMODITY_DESC.eq(category)&pool.IS_COMPLETE_WEEK]
        now=category_pool.loc[category_pool.WEEK_NO.isin(recent),"SALES_VALUE"].sum()
        before=category_pool.loc[category_pool.WEEK_NO.isin(previous),"SALES_VALUE"].sum()
        assert np.isclose(row.target_recent_revenue,now) and np.isclose(row.target_previous_revenue,before)
        assert np.isclose(row.target_recent_momentum,ratio(now,before),equal_nan=True)
        backtest=totals.loc[totals.COMMODITY_DESC.eq(category)]
        if len(backtest):
            selected_wape=direct_wape(backtest,"selected_forecast")
            baseline={name:direct_wape(backtest,column) for name,column in config.FORECAST_METHODS.items() if name!="Gradient boosting"}
            known={name:value for name,value in baseline.items() if np.isfinite(value)}
            best=min(known,key=lambda name:(known[name],name)) if known else None
            assert np.isclose(row.forecast_total_WAPE_pct,selected_wape,equal_nan=True)
            assert np.isclose(row.best_baseline_total_WAPE_pct,known[best] if best else np.nan,equal_nan=True)
            assert row.best_baseline==best and row.forecast_total_backtest_origins==len(backtest)
        else:
            assert pd.isna(row.forecast_total_WAPE_pct) and pd.isna(row.best_baseline_total_WAPE_pct)
        assert row.promotion_evidence_available==pd.notna(row.promotion_association)
    checks.append("Forecast totals and trailing/previous complete weeks, direct household-pool affinity/buyers/momentum and matched forecast-versus-baseline errors reconcile")

    top_sets={}
    for method,weights in [("forecast",config.REC_FORECAST_WEIGHTS),("segment",config.REC_SEGMENT_WEIGHTS)]:
        group=table.loc[table.candidate.eq(method)].set_index("COMMODITY_DESC")
        pd.testing.assert_frame_equal(group[evidence.columns].sort_index(),evidence.sort_index(),check_dtype=False)
        if method=="forecast":
            eligible=evidence.forecast_available & evidence.forecast_growth.notna() & np.isfinite(evidence.forecast_growth) & evidence.product_score.between(0,100)
            raw=evidence.forecast_growth
        else:
            eligible=evidence.target_affinity.notna() & evidence.target_recent_momentum.notna() & np.isfinite(evidence.target_affinity) & np.isfinite(evidence.target_recent_momentum) & evidence.target_buyers.ge(config.REC_MIN_TARGET_BUYERS)
            raw=evidence.target_affinity
        assert np.array_equal(group.loc[evidence.index,"eligible"],eligible)
        assert report["eligible_counts"][method]==int(eligible.sum())
        selected=evidence.loc[eligible]
        def normalized(values):
            if len(values)<2 or values.nunique()<2:
                return pd.Series(config.REC_NEUTRAL_RANK,index=values.index)
            return (values.rank(method="average")-1)/(len(values)-1)
        primary=normalized(raw.loc[selected.index])
        secondary=selected.product_score/config.CATEGORY_SCORE_SCALE if method=="forecast" else normalized(selected.target_recent_momentum)
        assert np.isclose(sum(weights.values()),1)
        expected_score=(primary*list(weights.values())[0]+secondary*list(weights.values())[1])*config.REC_SCORE_SCALE
        assert np.allclose(group.loc[selected.index,"component_primary"],primary)
        assert np.allclose(group.loc[selected.index,"component_secondary"],secondary)
        assert np.allclose(group.loc[selected.index,"recommendation_score"],expected_score)
        ordered=pd.DataFrame({"score":expected_score.to_numpy(),"COMMODITY_DESC":selected.index.to_numpy()}).sort_values(["score","COMMODITY_DESC"],ascending=[False,True])
        assert np.array_equal(group.loc[ordered.COMMODITY_DESC,"rank"].astype(int),np.arange(1,len(ordered)+1))
        assert group.loc[~group.index.isin(selected.index),"rank"].isna().all()
        assert group.loc[~group.index.isin(selected.index),"recommendation_score"].isna().all()
        for category,row in group.iterrows():
            label="maintain"
            growth=row.forecast_growth if method=="forecast" else row.target_recent_momentum
            if not row.eligible or growth < -config.REC_REVIEW_DECLINE:
                label="review"
            elif method=="forecast" and (pd.isna(row.forecast_total_WAPE_pct) or row.forecast_total_WAPE_pct>config.REC_MAX_FORECAST_WAPE):
                label="review"
            elif row["rank"]<=config.REC_DISPLAY_N and growth>=config.REC_PROMOTE_GROWTH and (method=="forecast" or row.target_affinity>=config.REC_PROMOTE_AFFINITY):
                label="promote"
            assert row.priority_label==label and row.execution_status=="review_required"
            assert row.promotion_evidence_status==("observational association" if row.promotion_evidence_available else "unavailable")
        assert report["priority_counts"][method]==group.priority_label.value_counts().to_dict()
        top_sets[method]=set(ordered.head(config.REC_DISPLAY_N).COMMODITY_DESC)
    shared=sorted(top_sets["forecast"]&top_sets["segment"])
    assert report["top10_shared_categories"]==shared and report["top10_overlap_count"]==len(shared)
    top=pd.read_csv(config.OUTPUTS_DIR/"recommendation_top10.csv")
    saved=table.loc[table.eligible & table["rank"].le(config.REC_DISPLAY_N)]
    assert len(top)==len(saved)
    assert set(zip(top.candidate,top.COMMODITY_DESC))==set(zip(saved.candidate,saved.COMMODITY_DESC))
    assert report["business_usefulness_review_complete"] is False and report["arbitration_implemented"] is False
    assert report["available_promotion_associations"]==int(evidence.promotion_evidence_available.sum())
    checks.append("Both independent eligibility rules, normalized components, weighted scores, ranks, provisional labels, review status and top-list overlap reproduce")
    write_json(config.REC_VALIDATION_FILE,{"status":"PASS","build_report_sha256":file_fingerprint(config.REC_BUILD_FILE)["sha256"],
        "checks":checks,"eligible_counts":report["eligible_counts"],"top10_overlap_count":len(shared),
        "business_usefulness_review_complete":False,"recommendation_accuracy_evaluated":False})
    print("PASS: independent recommendation arithmetic and source validation",flush=True)


if __name__=="__main__":
    main()

