"""Prepare and validate an isolated scope scenario; never apply it to the active project."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import numpy as np
import pandas as pd
from src import config
from src.aggregation import build_aggregate_frames
from src.artifact_io import file_fingerprint, write_json
from src.build_master import save_parquet
from src.data_access import load_processed_master
from src.judge import validate_answer
from src.scope import apply_scope_policy, normalize_names, policy_fingerprint
from src.scope_proposal import make_scope_proposal
from src.supervisor import route_question, run_specialist


def flattened(groups):
    return sorted({name for names in groups.values() for name in names})


def main():
    config_path = Path(config.__file__)
    active_before = {"configuration": file_fingerprint(config_path), "master": file_fingerprint(config.MASTER_FILE)}
    master = load_processed_master(require_scope=False)
    products = pd.read_parquet(config.PRODUCT_LOOKUP_FILE)
    proposal = make_scope_proposal(flattened(config.PROPOSED_SCOPE_DEPARTMENT_EXCLUSIONS), flattened(config.PROPOSED_SCOPE_COMMODITY_EXCLUSIONS), flattened(config.PROPOSED_SCOPE_DRUG_GM_EXCLUSIONS), "exclude", products)
    proposal["status"] = "ASSISTANT_PROPOSAL_REQUIRES_USER_REVIEW"
    proposal["note"] = "New proposed core-consumables boundary, not the missing historical scope. All scenario results remain unapproved. No active configuration or master data is changed."
    proposal["reference"] = config.PROPOSED_SCOPE_REFERENCE
    proposal["id"] = config.PROPOSED_SCOPE_ID
    policy = proposal["policy"]
    candidate = master.copy()
    candidate["IN_SCOPE"], candidate["DRUG_GM_REVIEW"] = apply_scope_policy(candidate, policy, products)
    departments = candidate.DEPARTMENT.astype("string").str.strip().str.upper()
    commodities = candidate.COMMODITY_DESC.astype("string").str.strip().str.upper()
    # Independent boolean benchmark for the proposed exclusion union.
    expected = ~departments.isin(normalize_names(policy["excluded_departments"])) & ~commodities.isin(normalize_names(policy["excluded_commodities"])) & ~(departments.eq("DRUG GM") & commodities.isin(normalize_names(policy["drug_gm_review_commodities"])))
    assert candidate.IN_SCOPE.astype(bool).equals(expected.astype(bool))
    daily, weekly, households, kpis, benchmarks = build_aggregate_frames(candidate)
    window = candidate.loc[candidate.IN_SCOPE & config.in_analysis_window(candidate)]
    assert kpis["baskets"] == window.BASKET_ID.nunique()
    assert kpis["households"] == window.household_key.nunique()
    assert np.isclose(kpis["revenue"], window.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    assert np.isclose(daily.loc[daily.in_window, "revenue"].sum(), window.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    assert np.isclose(weekly.loc[weekly.in_window, "revenue"].sum(), window.loc[window.IS_COMPLETE_WEEK, "SALES_VALUE"].sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    assert not daily.duplicated(["COMMODITY_DESC", "DATE"]).any()
    assert not weekly.duplicated(["COMMODITY_DESC", "WEEK_NO"]).any()
    directory = config.PROPOSED_SCOPE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    decisions = []
    for layer, groups in [("department", config.PROPOSED_SCOPE_DEPARTMENT_EXCLUSIONS), ("commodity", config.PROPOSED_SCOPE_COMMODITY_EXCLUSIONS), ("DRUG GM commodity", config.PROPOSED_SCOPE_DRUG_GM_EXCLUSIONS)]:
        for reason, names in groups.items():
            for name in names:
                decisions.append({"layer": layer, "name": name, "action": "proposed exclusion", "reason": reason})
    pd.DataFrame(decisions).to_csv(directory / "exclusion_rationale.csv", index=False)
    for name, frame in [("commodity_daily", daily), ("commodity_weekly", weekly), ("household_summary", households)]:
        save_parquet(frame, directory / f"{name}.parquet")
    kpis["status"] = "UNAPPROVED_SCOPE_SCENARIO_REAL_DATA"
    kpis["scope_id"] = config.PROPOSED_SCOPE_ID
    write_json(directory / "scenario_kpis.json", kpis)
    demo_results = []
    a, b = int(window.WEEK_NO.min()), int(window.WEEK_NO.max())
    for question in config.DEMO_QUESTIONS:
        decision = route_question(question)
        response = run_specialist(decision, candidate, products, a, b)
        response["evidence"]["result_status"] = "UNAPPROVED_SCOPE_SCENARIO_REAL_DATA"
        judgement = validate_answer(response, decision, a, b)
        assert judgement["accepted"], judgement
        demo_results.append({"question": question, "decision": decision, "response": response, "judge": judgement})
        print(f"PASS proposed-scope real-data tool + consistency Judge: {response['tool']}", flush=True)
    write_json(directory / "demo_evidence.json", {"status": "UNAPPROVED_SCOPE_SCENARIO_REAL_DATA", "note": "Passing consistency checks does not approve the business scope.", "results": demo_results})
    retained = candidate.loc[candidate.IN_SCOPE]
    excluded = candidate.loc[~candidate.IN_SCOPE]
    assert len(retained) + len(excluded) == len(master)
    assert np.isclose(retained.SALES_VALUE.sum() + excluded.SALES_VALUE.sum(), master.SALES_VALUE.sum(), rtol=0, atol=config.REVENUE_TOLERANCE_USD)
    proposal["selection_counts"] = {"Departments": len(policy["excluded_departments"]), "Commodities": len(policy["excluded_commodities"]), "DRUG GM review commodities": len(policy["drug_gm_review_commodities"])}
    proposal["impact"] = {"retained_source_lines": int(len(master)), "proposed_included_lines": int(len(retained)), "proposed_excluded_lines": int(len(excluded)), "retained_source_sales_usd": float(master.SALES_VALUE.sum()), "proposed_included_sales_usd": float(retained.SALES_VALUE.sum()), "proposed_excluded_sales_usd": float(excluded.SALES_VALUE.sum())}
    proposal["review_notes"] = config.PROPOSED_SCOPE_RETAINED_REVIEW_NOTES
    proposal["source_master_sha256"] = active_before["master"]["sha256"]
    proposal["source_lookup_sha256"] = file_fingerprint(config.PRODUCT_LOOKUP_FILE)["sha256"]
    proposal["active_policy_fingerprint"] = policy_fingerprint()
    write_json(directory / "scope_proposal.json", proposal)
    (directory / "scope_configuration.txt").write_text(proposal["configuration_block"], encoding="utf-8")
    active_after = {"configuration": file_fingerprint(config_path), "master": file_fingerprint(config.MASTER_FILE)}
    assert active_before == active_after, "An isolated proposal must not change active source/configuration"
    write_json(directory / "scenario_validation.json", {"status": "PASS_SCENARIO_NOT_APPROVED", "scope_id": config.PROPOSED_SCOPE_ID, "benchmarks": benchmarks, "checks": ["Explicit exclusion union matches independent benchmark", "Daily/full-week/window revenues reconcile", "KPI distinct counts and grid keys", "All five tools and consistency Judge", "Active configuration and master unchanged"], "active_snapshot": active_before, "note": "Actual real-data scenario calculations, not final project results or Review 3 values."})
    print("PASS: real aggregate scenario and all demo tools. Active configuration and master are unchanged.", flush=True)
    print(f"Review proposal, rationale and evidence in {directory}", flush=True)


if __name__ == "__main__":
    main()

