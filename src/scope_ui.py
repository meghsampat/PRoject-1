"""Scope review screen using processed product names and source audit evidence."""
import json
import pandas as pd
from src.artifact_io import file_fingerprint
import streamlit as st
from src import config
from src.scope_proposal import make_scope_proposal


def display_name(value):
    return value if value else "(blank label)"


def show_tested_proposal(products):
    proposal_path = config.PROPOSED_SCOPE_DIR / "scope_proposal.json"
    validation_path = config.PROPOSED_SCOPE_DIR / "scenario_validation.json"
    if not proposal_path.is_file() or not validation_path.is_file():
        return
    try:
        proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        master_validation = json.loads((config.OUTPUTS_DIR / "master_validation.json").read_text(encoding="utf-8"))
        if validation.get("status") != "PASS_SCENARIO_NOT_APPROVED" or proposal.get("source_master_sha256") != master_validation.get("master_sha256") or proposal.get("source_lookup_sha256") != file_fingerprint(config.PRODUCT_LOOKUP_FILE)["sha256"]:
            st.caption("The proposed scope needs regeneration for the current source snapshot.")
            return
        policy = proposal["policy"]
        checked = make_scope_proposal(policy["excluded_departments"], policy["excluded_commodities"], policy["drug_gm_review_commodities"], policy["drug_gm_policy"], products)
    except (OSError, KeyError, TypeError, ValueError):
        st.caption("The saved proposal could not be validated. You can still choose scope manually below.")
        return
    with st.expander("Tested FMCG scope proposal — awaiting review", expanded=True):
        st.write("A new proposed boundary covers groceries, personal care, household consumables and OTC health products. It is not a reconstruction of the missing historical scope. Mixed-category limitations are recorded below.")
        st.caption(f"Broad FMCG categories: {config.PROPOSED_SCOPE_REFERENCE}. Exact exclusions are documented project choices.")
        st.dataframe(pd.DataFrame([{"Selection": key, "Proposed exclusions": value} for key, value in proposal["selection_counts"].items()]), hide_index=True)
        impact = proposal["impact"]
        st.write("Scope impact across all retained source weeks, before applying the week-19 analysis window:")
        st.dataframe(pd.DataFrame([
            {"Candidate disposition": "Would include", "Transaction lines": impact["proposed_included_lines"], "Sales value (USD)": impact["proposed_included_sales_usd"]},
            {"Candidate disposition": "Would exclude", "Transaction lines": impact["proposed_excluded_lines"], "Sales value (USD)": impact["proposed_excluded_sales_usd"]},
        ]), hide_index=True)
        st.info("Scenario aggregates and all five tools passed consistency checks on real data. These remain unapproved scenario calculations; active business analytics are still blocked.")
        rationale_path = config.PROPOSED_SCOPE_DIR / "exclusion_rationale.csv"
        if rationale_path.is_file():
            st.dataframe(pd.read_csv(rationale_path, keep_default_na=False), hide_index=True)
            st.download_button("Download proposed exclusion rationale", rationale_path.read_bytes(), file_name="proposed_exclusion_rationale.csv", mime="text/csv")
        st.dataframe(pd.DataFrame([{"Retained category needing review": key, "Limitation": value} for key, value in proposal["review_notes"].items()]), hide_index=True)
        if st.button("Load tested proposal for review", key="load_tested_scope"):
            selected = checked["policy"]
            st.session_state["scope_departments"] = selected["excluded_departments"]
            st.session_state["scope_commodities"] = selected["excluded_commodities"]
            st.session_state["scope_drug_gm"] = selected["drug_gm_review_commodities"]
            st.session_state["scope_drug_gm_decision"] = selected["drug_gm_policy"].title()
            st.session_state["scope_reviewed"] = False
            st.session_state.pop("scope_draft", None)
            st.caption("Proposal loaded into the selectors below. Review the choices before generating a configuration block.")

def show_scope_selection():
    products = pd.read_parquet(config.PRODUCT_LOOKUP_FILE, columns=["DEPARTMENT", "COMMODITY_DESC"])
    departments = sorted(products.DEPARTMENT.astype("string").str.strip().str.upper().unique())
    commodities = sorted(products.COMMODITY_DESC.astype("string").str.strip().str.upper().unique())
    drug_gm = sorted(products.loc[products.DEPARTMENT.astype("string").str.strip().str.upper().eq("DRUG GM"), "COMMODITY_DESC"].astype("string").str.strip().str.upper().unique())
    st.subheader("Choose the analysis scope")
    st.write("Select the exclusions from the actual lookup. If you have the earlier definitions, use those names. You can also define a new scope explicitly; matching the guide's counts alone does not reproduce its missing lists.")
    show_tested_proposal(products)
    selected_departments = st.multiselect("Excluded departments", departments, format_func=display_name, key="scope_departments")
    selected_commodities = st.multiselect("Excluded commodities", commodities, format_func=display_name, key="scope_commodities")
    selected_drug_gm = st.multiselect("DRUG GM commodities for review", drug_gm, format_func=display_name, key="scope_drug_gm")
    decision = st.selectbox("Decision for selected DRUG GM commodities", ["Pending", "Keep", "Exclude"], key="scope_drug_gm_decision")
    st.caption("Commodity exclusions apply across departments. The DRUG GM decision applies to the selected commodities within DRUG GM only. Keeping a reviewed commodity does not override another exclusion.")
    counts = [len(selected_departments), len(selected_commodities), len(selected_drug_gm)]
    comparison = [{"Selection": label, "Chosen": chosen, "Earlier guide count": expected} for (label, expected), chosen in zip(config.DOCUMENTED_SCOPE_COUNTS.items(), counts)]
    st.dataframe(pd.DataFrame(comparison), hide_index=True)
    if any(row["Chosen"] != row["Earlier guide count"] for row in comparison):
        st.caption("Your counts differ from the guide. Check whether that is intentional before generating the draft.")
    with st.expander("Review the actual source audit tables"):
        st.caption("These are unscoped preparation-audit totals, not project KPIs. The tables describe retained transactions; selection options cover the full product lookup.")
        for filename, label in [("department_scope_audit.csv", "Department audit"), ("commodity_scope_audit.csv", "Commodity audit"), ("drug_gm_scope_audit.csv", "DRUG GM audit")]:
            path = config.OUTPUTS_DIR / filename
            if path.is_file():
                st.write(label)
                st.dataframe(pd.read_csv(path, keep_default_na=False), hide_index=True)
    selection_signature = (tuple(selected_departments), tuple(selected_commodities), tuple(selected_drug_gm), decision)
    if st.session_state.get("scope_last_selection") != selection_signature:
        st.session_state["scope_reviewed"] = False
        st.session_state["scope_last_selection"] = selection_signature
    reviewed = st.checkbox("I reviewed these scope choices, including any empty exclusion lists.", key="scope_reviewed")
    signature = (tuple(selected_departments), tuple(selected_commodities), tuple(selected_drug_gm), decision, reviewed)
    previous = st.session_state.get("scope_draft")
    if previous and previous["signature"] != signature:
        st.session_state.pop("scope_draft", None)
    if st.button("Generate scope configuration", disabled=not reviewed or decision == "Pending", key="generate_scope"):
        proposal = make_scope_proposal(selected_departments, selected_commodities, selected_drug_gm, decision.lower(), products)
        st.session_state.scope_draft = {"signature": signature, "proposal": proposal}
    draft = st.session_state.get("scope_draft")
    if draft:
        st.info("Draft generated. Configuration and processed data have not changed.")
        st.code(draft["proposal"]["configuration_block"], language="python")
        st.download_button("Download configuration block", draft["proposal"]["configuration_block"], file_name="scope_configuration.txt", mime="text/plain")
        st.write("Replace the four matching assignments in src/config.py with this block. Then rebuild and validate:")
        st.code(".\\.venv\\Scripts\\python.exe src/build_master.py\n.\\.venv\\Scripts\\python.exe src/validate_master.py\n.\\.venv\\Scripts\\python.exe src/build_aggregates.py\n.\\.venv\\Scripts\\python.exe src/validate_aggregates.py", language="powershell")
        st.caption("You can also paste the generated block into this chat so the configuration and rebuild can be applied here. Weighted-product classification remains a separate pending definition.")


