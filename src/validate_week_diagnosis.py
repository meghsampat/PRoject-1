"""Independent week totals, distinct-counts, contribution and descriptive breadth checks."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint,write_json
from src.data_access import load_analysis_transactions,load_validated_aggregate
from src.diagnostic_access import load_diagnostic_report


def main():
    report=load_diagnostic_report(require_validation=False)
    data=load_analysis_transactions()
    week=report["week"]; references=report["reference_weeks"]
    assert week==config.DIAG_TARGET_WEEK and references==[w for w in range(week-config.DIAG_NEIGHBOR_RADIUS,week+config.DIAG_NEIGHBOR_RADIUS+1) if w!=week]
    study=data.loc[data.IS_COMPLETE_WEEK & data.WEEK_NO.isin(references+[week])]
    assert study.SOURCE_ROW_ID.is_unique and set(study.WEEK_NO)==set(references+[week])
    weekly=pd.read_csv(config.OUTPUTS_DIR/config.DIAG_TABLE_FILES["weekly"]).set_index("WEEK_NO")
    for w in references+[week]:
        source=study.loc[study.WEEK_NO.eq(w)]
        row=weekly.loc[w]
        assert np.isclose(row.revenue,source.SALES_VALUE.sum())
        assert row.baskets==source.BASKET_ID.nunique() and row.households==source.household_key.nunique()
        assert row.transaction_lines==len(source) and row.observed_days==source.DAY.nunique()
        assert np.isclose(row.average_basket_value,row.revenue/row.baskets)
    macro=report["macro"]
    for name in ["revenue","baskets","households","transaction_lines"]:
        baseline=weekly.loc[references,name].sum()/len(references)
        assert np.isclose(macro[name],weekly.loc[week,name]) and np.isclose(macro["reference_"+name],baseline)
        assert np.isclose(macro[name+"_change_pct"],(macro[name]/baseline-1)*100)
    assert np.isclose(macro["delta_revenue"],macro["revenue"]-macro["reference_revenue"])
    assert np.isclose(macro["average_basket_value"],macro["revenue"]/macro["baskets"])
    assert np.isclose(macro["reference_average_basket_value"],macro["reference_revenue"]/macro["reference_baskets"])
    assert np.isclose(macro["average_basket_value_change_pct"],(macro["average_basket_value"]/macro["reference_average_basket_value"]-1)*100)
    assert np.isclose((1+macro["baskets_change_pct"]/100)*(1+macro["average_basket_value_change_pct"]/100)-1,macro["revenue_change_pct"]/100)
    for flag in config.DIAG_FLAGS:
        assert report["flags"][flag]==int(study.loc[study.WEEK_NO.eq(week),flag].sum())
    aggregate=load_validated_aggregate("commodity_weekly")
    for w in references+[week]:
        assert np.isclose(weekly.loc[w,"revenue"],aggregate.loc[aggregate.WEEK_NO.eq(w),"revenue"].sum(),atol=config.REVENUE_TOLERANCE_USD,rtol=0)
    groups={}
    for label,key in [("department","DEPARTMENT"),("store","STORE_ID"),("commodity","COMMODITY_DESC")]:
        table=pd.read_csv(config.OUTPUTS_DIR/config.DIAG_TABLE_FILES[label])
        assert table[key].is_unique and set(table[key])==set(study[key])
        for row in table.to_dict("records"):
            source=study.loc[study[key].eq(row[key])]
            target=source.loc[source.WEEK_NO.eq(week)]
            before=source.loc[source.WEEK_NO.isin(references)]
            reference=before.SALES_VALUE.sum()/len(references)
            assert np.isclose(row["target_revenue"],target.SALES_VALUE.sum())
            assert np.isclose(row["reference_mean_revenue"],reference)
            assert row["target_lines"]==len(target) and np.isclose(row["reference_mean_lines"],len(before)/len(references))
            assert np.isclose(row["delta_revenue"],row["target_revenue"]-reference)
            assert np.isclose(row["change_pct"],(row["target_revenue"]/reference-1)*100 if reference>0 else np.nan,equal_nan=True)
        assert np.isclose(table.target_revenue.sum(),macro["revenue"],atol=config.REVENUE_TOLERANCE_USD,rtol=0)
        assert np.isclose(table.reference_mean_revenue.sum(),macro["reference_revenue"],atol=config.REVENUE_TOLERANCE_USD,rtol=0)
        assert np.isclose(table.delta_revenue.sum(),macro["delta_revenue"])
        positive=table.delta_revenue.clip(lower=0)
        assert np.allclose(table.positive_delta_share,positive/positive.sum())
        assert np.allclose(table.target_revenue_share,table.target_revenue/macro["revenue"])
        assert np.allclose(table.reference_revenue_share,table.reference_mean_revenue/macro["reference_revenue"])
        groups[label]=table
    major=groups["department"].loc[groups["department"].reference_revenue_share.ge(config.DIAG_MAJOR_DEPT_SHARE)]
    stores=groups["store"].loc[groups["store"].reference_mean_revenue.ge(config.DIAG_MIN_STORE_BASELINE)]
    breadth=report["breadth"]
    assert breadth["major_departments"]==len(major) and breadth["positive_major_departments"]==major.delta_revenue.gt(0).sum()
    assert breadth["eligible_stores"]==len(stores) and breadth["positive_eligible_stores"]==stores.delta_revenue.gt(0).sum()
    assert np.isclose(breadth["positive_store_fraction"],stores.delta_revenue.gt(0).mean())
    assert np.isclose(breadth["positive_department_baseline_share"],major.loc[major.delta_revenue.gt(0),"reference_mean_revenue"].sum()/major.reference_mean_revenue.sum())
    assert np.isclose(breadth["top_store_positive_delta_share"],groups["store"].positive_delta_share.max())
    assert np.isclose(breadth["top_department_positive_delta_share"],groups["department"].positive_delta_share.max())
    expected=(breadth["positive_major_departments"]>=config.DIAG_MIN_POSITIVE_DEPTS and breadth["positive_store_fraction"]>=config.DIAG_MIN_POSITIVE_STORE_FRACTION
              and breadth["positive_department_baseline_share"]>=config.DIAG_MIN_POSITIVE_DEPT_BASELINE_SHARE and breadth["top_store_positive_delta_share"]<=config.DIAG_MAX_TOP_STORE_DELTA_SHARE)
    assert breadth["broad_pattern"]==bool(expected) and report["cause_verified"] is False
    assert report["classification"]==("broad_observed_sales_pattern" if expected else "concentrated_or_inconclusive_pattern")
    write_json(config.DIAG_VALIDATION_FILE,{"status":"PASS","build_report_sha256":file_fingerprint(config.DIAG_REPORT_FILE)["sha256"],
        "checks":["Exact weekly revenue/distinct counts/flags and aggregate benchmark reconcile","All department/store/category changes and positive-change denominators independently reproduce","Basket-value decomposition and descriptive breadth criteria reproduce; no cause or corruption inferred"],
        "decision":"Retain week records without adjustment","cause_verified":False})
    print("PASS: independent week diagnosis validation",flush=True)


if __name__=="__main__":
    main()
