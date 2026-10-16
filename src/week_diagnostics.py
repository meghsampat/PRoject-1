"""Describe a sales deviation without inferring a holiday, causality or corrupt data."""
import hashlib
import json
import numpy as np
import pandas as pd
from src import config


def settings_fingerprint():
    names=["DIAG_TARGET_WEEK","DIAG_NEIGHBOR_RADIUS","DIAG_MIN_STORE_BASELINE","DIAG_MAJOR_DEPT_SHARE",
           "DIAG_MIN_POSITIVE_DEPTS","DIAG_MIN_POSITIVE_STORE_FRACTION","DIAG_MIN_POSITIVE_DEPT_BASELINE_SHARE",
           "DIAG_MAX_TOP_STORE_DELTA_SHARE","DIAG_FLAGS"]
    return hashlib.sha256(json.dumps({name:getattr(config,name) for name in names},sort_keys=True).encode()).hexdigest()


def change_pct(target,baseline):
    return float((target/baseline-1)*100) if baseline>0 else None


def reference_weeks(week):
    return [w for w in range(week-config.DIAG_NEIGHBOR_RADIUS,week+config.DIAG_NEIGHBOR_RADIUS+1) if w!=week]


def weekly_summary(data):
    result=data.groupby("WEEK_NO").agg(revenue=("SALES_VALUE","sum"),baskets=("BASKET_ID","nunique"),
        households=("household_key","nunique"),transaction_lines=("SOURCE_ROW_ID","size"),observed_days=("DAY","nunique")).reset_index()
    result["average_basket_value"]=result.revenue/result.baskets.replace(0,np.nan)
    return result


def group_contribution(data,key,week,references):
    revenue=data.groupby([key,"WEEK_NO"]).SALES_VALUE.sum().unstack(fill_value=0).reindex(columns=references+[week],fill_value=0)
    lines=data.groupby([key,"WEEK_NO"]).size().unstack(fill_value=0).reindex(index=revenue.index,columns=references+[week],fill_value=0)
    result=pd.DataFrame({key:revenue.index,"target_revenue":revenue[week].to_numpy(),
        "reference_mean_revenue":revenue[references].mean(axis=1).to_numpy(),
        "target_lines":lines[week].to_numpy(),"reference_mean_lines":lines[references].mean(axis=1).to_numpy()})
    result["delta_revenue"]=result.target_revenue-result.reference_mean_revenue
    result["change_pct"]=(result.target_revenue/result.reference_mean_revenue.replace(0,np.nan)-1)*100
    result["target_revenue_share"]=result.target_revenue/result.target_revenue.sum() if result.target_revenue.sum()>0 else np.nan
    result["reference_revenue_share"]=result.reference_mean_revenue/result.reference_mean_revenue.sum() if result.reference_mean_revenue.sum()>0 else np.nan
    positive=result.delta_revenue.clip(lower=0)
    result["positive_delta_share"]=positive/positive.sum() if positive.sum()>0 else np.nan
    return result.sort_values(["delta_revenue",key],ascending=[False,True]).reset_index(drop=True)


def breadth_summary(departments,stores):
    major=departments.loc[departments.reference_revenue_share.ge(config.DIAG_MAJOR_DEPT_SHARE)]
    eligible=stores.loc[stores.reference_mean_revenue.ge(config.DIAG_MIN_STORE_BASELINE)]
    positive_store_fraction=float(eligible.delta_revenue.gt(0).mean()) if len(eligible) else None
    positive_dept_share=float(major.loc[major.delta_revenue.gt(0),"reference_mean_revenue"].sum()/major.reference_mean_revenue.sum()) if major.reference_mean_revenue.sum()>0 else None
    store_top=stores.positive_delta_share.max()
    dept_top=departments.positive_delta_share.max()
    broad=(len(major.loc[major.delta_revenue.gt(0)])>=config.DIAG_MIN_POSITIVE_DEPTS
           and positive_store_fraction is not None and positive_store_fraction>=config.DIAG_MIN_POSITIVE_STORE_FRACTION
           and positive_dept_share is not None and positive_dept_share>=config.DIAG_MIN_POSITIVE_DEPT_BASELINE_SHARE
           and pd.notna(store_top) and store_top<=config.DIAG_MAX_TOP_STORE_DELTA_SHARE)
    return {"eligible_stores":len(eligible),"positive_eligible_stores":int(eligible.delta_revenue.gt(0).sum()),
        "positive_store_fraction":positive_store_fraction,"major_departments":len(major),
        "positive_major_departments":int(major.delta_revenue.gt(0).sum()),"positive_department_baseline_share":positive_dept_share,
        "top_store_positive_delta_share":float(store_top) if pd.notna(store_top) else None,
        "top_department_positive_delta_share":float(dept_top) if pd.notna(dept_top) else None,
        "broad_pattern":bool(broad)}


def diagnose_week(data):
    required=["IN_SCOPE","IS_COMPLETE_WEEK","WEEK_NO","SALES_VALUE","DEPARTMENT","STORE_ID","COMMODITY_DESC",
              "SOURCE_ROW_ID","BASKET_ID","household_key","DAY",*config.DIAG_FLAGS]
    if any(name not in data for name in required) or data[required].isna().any().any():
        raise ValueError("Week diagnostics need nonmissing prepared scope, provenance, sales and flag columns.")
    window=data.loc[data.IN_SCOPE & data.IS_COMPLETE_WEEK & config.in_analysis_window(data)]
    week=config.DIAG_TARGET_WEEK
    references=reference_weeks(week)
    study=window.loc[window.WEEK_NO.isin(references+[week])]
    if set(study.WEEK_NO)!=set(references+[week]):
        raise ValueError("Target and every neighbouring reference week must be complete and available in the analysis window.")
    if not study.SOURCE_ROW_ID.is_unique or not np.isfinite(study.SALES_VALUE).all():
        raise ValueError("Duplicate prepared source-row IDs or nonfinite revenue; investigate source integrity.")
    weekly=weekly_summary(study)
    target=weekly.loc[weekly.WEEK_NO.eq(week)].iloc[0]
    reference=weekly.loc[weekly.WEEK_NO.isin(references)]
    macro={}
    for name in ["revenue","baskets","households","transaction_lines"]:
        before=float(reference[name].mean())
        after=float(target[name])
        macro[name]=after
        macro["reference_"+name]=before
        macro[name+"_change_pct"]=change_pct(after,before)
    macro["delta_revenue"]=macro["revenue"]-macro["reference_revenue"]
    # Pooled reference ABV, not an unweighted mean of per-week ratios.
    macro["average_basket_value"]=macro["revenue"]/macro["baskets"]
    macro["reference_average_basket_value"]=macro["reference_revenue"]/macro["reference_baskets"]
    macro["average_basket_value_change_pct"]=change_pct(macro["average_basket_value"],macro["reference_average_basket_value"])
    groups={name:group_contribution(study,key,week,references) for name,key in
            [("department","DEPARTMENT"),("store","STORE_ID"),("commodity","COMMODITY_DESC")]}
    breadth=breadth_summary(groups["department"],groups["store"])
    flags={name:int(study.loc[study.WEEK_NO.eq(week),name].sum()) for name in config.DIAG_FLAGS}
    return weekly,groups,{"week":week,"reference_weeks":references,"macro":macro,"breadth":breadth,"flags":flags,
        "classification":"broad_observed_sales_pattern" if breadth["broad_pattern"] else "concentrated_or_inconclusive_pattern",
        "decision":"Retain all week records without adjustment under the accepted cleaning policy",
        "cause_verified":False,
        "interpretation":"Observed changes span stores and major departments; no isolated-store artefact is established. Cause remains unknown."
            if breadth["broad_pattern"] else "Observed concentration requires review; a concentration alone does not establish corrupt data or justify deleting records."}
