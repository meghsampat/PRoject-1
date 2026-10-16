"""Checks of distinct-count baselines, concentration and unknown diagnostic causes."""
import unittest
import numpy as np
import pandas as pd
from src import config
from src.week_diagnostics import diagnose_week,group_contribution,change_pct


def fixture(single_store=False):
    rows=[]
    reference=[90,91,92,93,94]
    for week in reference:
        for day in range(7):
            for store in range(1,5):
                for department in range(4):
                    uplift=(2. if store==1 else 1.) if single_store else 1.25
                    rows.append({"WEEK_NO":week,"DAY":week*7+day,"STORE_ID":store,"DEPARTMENT":f"D{department}",
                        "COMMODITY_DESC":f"C{department}","BASKET_ID":week*10000+day*100+store,"household_key":day,
                        "SOURCE_ROW_ID":len(rows),"SALES_VALUE":100.*(uplift if week==92 else 1.),
                        "IN_SCOPE":True,"IS_COMPLETE_WEEK":True,**{name:False for name in config.DIAG_FLAGS}})
    return pd.DataFrame(rows)


class WeekDiagnosticTests(unittest.TestCase):
    def test_broad_uplift_and_distinct_baskets_not_added_by_department(self):
        weekly,groups,report=diagnose_week(fixture())
        self.assertAlmostEqual(report["macro"]["revenue_change_pct"],25)
        self.assertEqual(report["macro"]["baskets"],28)
        self.assertAlmostEqual(report["macro"]["average_basket_value_change_pct"],25)
        self.assertTrue(report["breadth"]["broad_pattern"])
        self.assertFalse(report["cause_verified"])
        self.assertAlmostEqual(groups["department"].delta_revenue.sum(),report["macro"]["delta_revenue"])

    def test_single_store_concentration_is_review_not_proven_corruption(self):
        _,_,report=diagnose_week(fixture(single_store=True))
        self.assertFalse(report["breadth"]["broad_pattern"])
        self.assertEqual(report["breadth"]["top_store_positive_delta_share"],1)
        self.assertFalse(report["cause_verified"])
        self.assertIn("Retain",report["decision"])

    def test_zero_reference_group_growth_stays_unknown(self):
        data=fixture()
        data.loc[data.WEEK_NO.eq(92),"DEPARTMENT"]="new"
        groups=group_contribution(data,"DEPARTMENT",92,[90,91,93,94])
        self.assertTrue(pd.isna(groups.loc[groups.DEPARTMENT.eq("new"),"change_pct"].iloc[0]))
        self.assertIsNone(change_pct(10,0))

    def test_missing_week_or_duplicate_source_id_is_rejected(self):
        data=fixture()
        with self.assertRaises(ValueError):diagnose_week(data.loc[data.WEEK_NO.ne(91)])
        data.loc[1,"SOURCE_ROW_ID"]=data.loc[0,"SOURCE_ROW_ID"]
        with self.assertRaises(ValueError):diagnose_week(data)

    def test_out_of_scope_and_partial_rows_do_not_inflate_diagnosis(self):
        data=fixture()
        extra=data.head(1).copy()
        extra["SALES_VALUE"]=1e6
        extra["SOURCE_ROW_ID"]=10000
        extra["IN_SCOPE"]=False
        _,_,before=diagnose_week(data)
        _,_,after=diagnose_week(pd.concat([data,extra]))
        self.assertEqual(before["macro"],after["macro"])


if __name__=="__main__":unittest.main()
