"""Local-only FMCG dashboard for VS Code; no cloud service is used."""
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from src import config
from src.dashboard_ui import shell, weekly_revenue, overview, transparency
from src.chat_assistant import run_chat_turn, verify_chat_blocks
from src.config import DEMO_QUESTIONS, MASTER_FILE, OUTPUTS_DIR, PRODUCT_LOOKUP_FILE, SEGMENT_BUILD_FILE, SEGMENT_VALIDATION_FILE, CATEGORY_BUILD_FILE, CATEGORY_VALIDATION_FILE, FORECAST_BUILD_FILE, FORECAST_VALIDATION_FILE, REC_BUILD_FILE, REC_VALIDATION_FILE, DIAG_REPORT_FILE, DIAG_VALIDATION_FILE
from src.data_access import load_products, load_analysis_transactions
from src.scope import ScopeNotConfiguredError, policy_fingerprint
from src.tools import query_sales_kpis
from src.scope_ui import show_scope_selection

st.set_page_config(page_title="FMCG Product Intelligence", layout="wide")
shell()



@st.cache_data(show_spinner="Loading transaction data...")
def cached_transactions(file_path, modified_time):
    return load_analysis_transactions()


@st.cache_data(show_spinner=False)
def cached_products(file_path, modified_time):
    return load_products(file_path)


@st.cache_data(show_spinner=False)
def cached_kpis(file_signature, start_week, end_week, _data):
    # Cache identity includes source modification time and scope; _data avoids rehashing a large frame.
    return query_sales_kpis(_data, start_week, end_week)


def show_visuals(response):
    evidence, tool = response["evidence"], response["tool"]
    if tool == "query_sales_kpis":
        st.dataframe(pd.DataFrame([response["claims"]]), hide_index=True)
        return
    rows = pd.DataFrame(evidence["rows"])
    if tool == "get_sales_trend":
        figure = px.line(rows, x="WEEK_NO", y="revenue", markers=True, labels={"WEEK_NO": "Dataset week", "revenue": "Revenue (USD)"}, title="Observed weekly sales")
        st.plotly_chart(figure, width="stretch")
    elif tool == "get_week_diagnosis":
        departments = pd.DataFrame(evidence["department_rows"])
        figure = px.bar(departments, x="DEPARTMENT", y="delta_revenue",
                        labels={"delta_revenue": "Revenue difference from neighbour mean (USD)"},
                        title=f"Dataset week {evidence['week']}: department contributions")
        st.plotly_chart(figure, width="stretch")
        st.dataframe(departments[["DEPARTMENT","target_revenue","reference_mean_revenue","delta_revenue","change_pct"]], hide_index=True)
        breadth = evidence["breadth"]
        st.caption(f"Positive changes: {breadth['positive_eligible_stores']} of {breadth['eligible_stores']} eligible stores; {breadth['positive_major_departments']} of {breadth['major_departments']} major departments. Largest store share of positive changes: {breadth['top_store_positive_delta_share']:.2%}.")
        with st.expander("Largest store contributions"):
            st.dataframe(pd.DataFrame(evidence["store_rows"]), hide_index=True)
        st.info(evidence["decision"] + ". Cause remains unverified.")
    elif tool == "get_product_performance":
        chart_rows = rows.copy()
        chart_rows["Product"] = chart_rows.PRODUCT_ID.astype(str)
        figure = px.bar(chart_rows, x="Product", y="revenue", hover_data=["COMMODITY_DESC", "SUB_COMMODITY_DESC"], labels={"revenue": "Revenue (USD)"}, title="Top products by revenue")
        st.plotly_chart(figure, width="stretch")
    elif tool == "get_category_intelligence":
        figure = px.bar(rows.head(20), x="COMMODITY_DESC", y="score", hover_data=["minimum_rank", "maximum_rank"],
                        labels={"COMMODITY_DESC": "Commodity", "score": "Composite index (0-100)"},
                        title="Category intelligence: top 20")
        st.plotly_chart(figure, width="stretch")
        st.caption(f"Promotion records cover {evidence['promotion_coverage_share']:.1%} of observed sold product/store/week keys. Missing comparisons remain unknown.")
        if evidence["promotion_associations_available"] == 0:
            st.info("No scored category meets the promotion comparison guards. Every promotion component is neutral; this ranking currently differentiates categories using the other five components.")
        st.write("Component weights")
        st.dataframe(pd.DataFrame([{"Component": name.replace("_", " "), "Weight": weight} for name, weight in evidence["weights"].items()]), hide_index=True)
        sensitivity = evidence["sensitivity"]
        st.caption(f"100 weight perturbations (+/-20% before renormalizing): minimum full-ranking Spearman {sensitivity['spearman_all_min']:.4f}; minimum top-20 retention {sensitivity['top20_overlap_min']:.0%}.")
        rows = rows[["COMMODITY_DESC", "rank", "score", "revenue", "buyers", "repeat_purchase_rate",
                     "growth", "yoy_growth", "promotion_association", "promotion_reason", "minimum_rank", "maximum_rank"]]
    elif tool == "get_customer_segments":
        if evidence.get("mode") == "saved_model":
            figure = go.Figure()
            figure.add_bar(x=rows.segment_name, y=rows.household_share_pct, name="Household share")
            figure.add_bar(x=rows.segment_name, y=rows.revenue_share_pct, name="Revenue share")
            figure.update_layout(title="Segment household share versus revenue share", yaxis_title="Share (%)", barmode="group")
        else:
            figure = px.bar(rows, x="segment", y="households", labels={"segment": "Exploratory segment", "households": "Households"}, title="Customer segment sizes")
        st.plotly_chart(figure, width="stretch")
        st.caption(evidence["method"])
        if evidence.get("mode") == "saved_model":
            st.caption(f"Saved-model validation: PASS. Mean initialization ARI: {evidence['stability_mean_ari']:.4f}. Business names/actions are provisional.")
        st.write("Candidate cluster evaluation")
        st.dataframe(pd.DataFrame(evidence["evaluation"]), hide_index=True)
    elif tool == "get_recommendations":
        figure = px.bar(rows, x="recommendation_score", y="COMMODITY_DESC", orientation="h",
                        facet_col="candidate", color="priority_label",
                        labels={"recommendation_score": "Within-method priority index (0-100)", "COMMODITY_DESC": "Commodity"},
                        title="Two recommendation hypotheses")
        figure.update_yaxes(matches=None)
        st.plotly_chart(figure, width="stretch")
        st.caption(f"Shared top-10 categories: {', '.join(evidence['shared_top10_categories']) or 'none'}. Both lists remain available for review; no automatic winner is chosen.")
        st.info("Promote is a provisional hypothesis for a measured test. All candidates require review; no promotion effect, profit or ROI is established.")
        columns = ["rank", "COMMODITY_DESC", "recommendation_score", "priority_label",
                   "forecast_growth", "product_score", "target_affinity", "target_recent_momentum",
                   "target_buyers", "forecast_total_WAPE_pct", "best_baseline_total_WAPE_pct",
                   "promotion_evidence_status", "execution_status"]
        for method, title in [("forecast", "Forecast growth and category score"), ("segment", "Observed spending-group affinity and momentum")]:
            st.write(title)
            st.dataframe(rows.loc[rows.candidate.eq(method), columns], hide_index=True)
        st.caption(f"Target spending group: {evidence['target_households']:,} households. Snapshot ends at week {evidence['as_of_week']}; forecast target overlaps partial source weeks {evidence['partial_forecast_overlap']}.")
        st.info(evidence["note"])
        return
    elif tool == "forecast_demand":
        history = pd.DataFrame(evidence["history"])
        figure = go.Figure()
        figure.add_scatter(x=history.week, y=history.revenue, name="Observed complete-week revenue", mode="lines")
        forecast_name = "Validation-selected forecast" if evidence.get("mode") == "saved_direct_model" else "Moving-average forecast"
        figure.add_scatter(x=rows.week, y=rows.forecast_revenue, name=forecast_name, mode="lines+markers", line={"dash": "dash"})
        if evidence.get("mode") == "saved_direct_model":
            figure.add_scatter(x=rows.week, y=rows.trained_revenue, name="Direct gradient boosting", mode="lines+markers", line={"dash": "dot"})
        figure.update_layout(title=f"Weekly revenue outlook: {evidence['category']}", xaxis_title="Dataset week", yaxis_title="Revenue (USD)")
        st.plotly_chart(figure, width="stretch")
        if evidence.get("mode") == "saved_direct_model":
            st.write("Held-out revenue: trained model versus three baselines at horizons 1-4")
            st.caption("MAE/RMSE are USD; MAPE excludes zero actuals. WAPE is absolute error / absolute revenue. Each method uses identical origins/targets per horizon. Horizons 1-4 have 12/11/10/9 evaluable origins; methods were selected on earlier validation.")
            st.write("Four-week revenue totals: nine common held-out origins")
            st.dataframe(pd.DataFrame(evidence["four_week_evaluation"]), hide_index=True)
        else:
            st.write("Last 12 complete weeks: rolling one-step baseline comparison")
            st.caption("MAE and RMSE are in USD. MAPE excludes zero-actual weeks; WAPE uses absolute actual revenue. Undefined metrics appear blank. These are not four-step accuracy metrics.")
        st.dataframe(pd.DataFrame(evidence["evaluation"]), hide_index=True)
        st.caption(f"Forecast method: {evidence['model']}. Excluded partial weeks: {evidence['excluded_partial_weeks']}. Seasonal baseline available: {evidence['seasonal_baseline_available']}.")
        with st.expander("Holdout evidence"):
            st.dataframe(pd.DataFrame(evidence["holdout"]), hide_index=True)
    st.dataframe(rows, hide_index=True)
    if evidence.get("note"):
        st.info(evidence["note"])


try:
    transaction_signature = (MASTER_FILE.stat().st_mtime_ns, policy_fingerprint(), (OUTPUTS_DIR / "master_validation.json").stat().st_mtime_ns)
    data = cached_transactions(MASTER_FILE, transaction_signature)
    first_week, last_week = int(data.WEEK_NO.min()), int(data.WEEK_NO.max())
    with st.sidebar:
        st.header("Analysis scope")
        start_week = int(st.number_input("Start week", min_value=first_week, max_value=last_week, value=first_week, step=1))
        end_week = int(st.number_input("End week", min_value=first_week, max_value=last_week, value=last_week, step=1))
        st.caption("Both bounds are inclusive. KPI records are retained, including flagged records. Forecasting separately excludes partial weeks and reports them.")
    result = cached_kpis(transaction_signature, start_week, end_week, data)
    overview_tab, assistant_tab, customers_tab, forecasts_tab = st.tabs(["Overview", "AI Assistant", "Customers", "Forecasts"])
    with overview_tab:
        st.subheader("Executive Overview")
        st.caption("Retail performance from your validated data")
        columns = st.columns(4)
        columns[0].metric("Total Revenue (USD)", f"${result['revenue']:,.2f}")
        columns[1].metric("Total Baskets", f"{result['baskets']:,}")
        columns[2].metric("Total Households", f"{result['households']:,}")
        columns[3].metric("Average Basket Value (USD)", f"${result['average_basket_value']:,.2f}")
        st.write(f"Weeks {start_week} to {end_week} contain {result['transaction_lines']:,} transaction lines. Revenue uses SALES_VALUE; average basket value divides revenue by unique BASKET_ID count.")

        overview(weekly_revenue(transaction_signature, start_week, end_week, data))

    # Chat history is scoped to the validated snapshot, never reused across data changes.
    # Product lookup is loaded only for the tools that need it.
    product_signature = PRODUCT_LOOKUP_FILE.stat().st_mtime_ns if PRODUCT_LOOKUP_FILE.exists() else None
    segment_signature = (SEGMENT_BUILD_FILE.stat().st_mtime_ns if SEGMENT_BUILD_FILE.exists() else None, SEGMENT_VALIDATION_FILE.stat().st_mtime_ns if SEGMENT_VALIDATION_FILE.exists() else None)
    category_signature = (CATEGORY_BUILD_FILE.stat().st_mtime_ns if CATEGORY_BUILD_FILE.exists() else None, CATEGORY_VALIDATION_FILE.stat().st_mtime_ns if CATEGORY_VALIDATION_FILE.exists() else None)
    forecast_signature = (FORECAST_BUILD_FILE.stat().st_mtime_ns if FORECAST_BUILD_FILE.exists() else None, FORECAST_VALIDATION_FILE.stat().st_mtime_ns if FORECAST_VALIDATION_FILE.exists() else None)
    recommendation_signature = (REC_BUILD_FILE.stat().st_mtime_ns if REC_BUILD_FILE.exists() else None, REC_VALIDATION_FILE.stat().st_mtime_ns if REC_VALIDATION_FILE.exists() else None)
    diagnostic_signature = (DIAG_REPORT_FILE.stat().st_mtime_ns if DIAG_REPORT_FILE.exists() else None, DIAG_VALIDATION_FILE.stat().st_mtime_ns if DIAG_VALIDATION_FILE.exists() else None)
    scope_signature = (transaction_signature, product_signature, segment_signature, category_signature, forecast_signature, recommendation_signature, diagnostic_signature, start_week, end_week, config.CHAT_PRESENTATION_VERSION)
    if st.session_state.get("chat_signature") != scope_signature:
        previous = st.session_state.get("chat_signature")
        st.session_state.messages = []
        st.session_state.pop("pending_chat", None)
        st.session_state.pop("analysis", None)
        st.session_state.chat_signature = scope_signature
        if previous is not None:
            st.info("The data or week scope changed. A new conversation has started.")
    messages = st.session_state.messages
    request = st.session_state.pop("pending_chat", None)
    with assistant_tab:
        conversation, trace_panel = st.columns([2.3, 1])
        with conversation:
            st.subheader("AI Business Assistant")
            st.caption("Ask a question, explore the evidence, then ask a follow-up.")
            with st.expander("Example questions"):
                selected_demo = st.selectbox("Demo question", DEMO_QUESTIONS)
                with st.form("manager_question"):
                    question = st.text_input("Manager question", value=selected_demo, key=f"question_{selected_demo}")
                    submitted = st.form_submit_button("Analyse")
                if submitted:
                    request = question
            with st.sidebar:
                st.divider()
                st.subheader("Assistant")
                response_mode = st.radio("Answer length", config.CHAT_RESPONSE_MODES, index=0, key="answer_length")
                st.caption("Runs on your computer. No cloud account or deployment is needed.")
                if st.button("New conversation", key="new_conversation"):
                    messages.clear()
                    st.session_state.pop("analysis", None)
                st.caption("Conversation stays in this browser session and resets when data or week scope changes.")
            if not messages:
                st.markdown("Ask about your sales, customers or product opportunities. I’ll show the supporting data and suggest what to review next.")
                starters = st.columns(len(config.CHAT_STARTERS))
                for column, prompt in zip(starters, config.CHAT_STARTERS):
                    if column.button(prompt, key="starter_" + prompt):
                        request = prompt

            chat_request = st.chat_input("Ask about sales, customers, forecasts or next steps…", max_chars=config.CHAT_MAX_INPUT_CHARS)
            if chat_request:
                request = chat_request
            if request:
                st.session_state.pop("analysis", None)
                context = next((message["turn"] for message in reversed(messages)
                                if message.get("turn", {}).get("status") == "accepted"), None)
                messages.append({"role": "user", "content": request})
                try:
                    with st.spinner("Checking the data and preparing suggestions…"):
                        turn = run_chat_turn(request, data,
                            lambda: cached_products(PRODUCT_LOOKUP_FILE, product_signature),
                            start_week, end_week, context)
                    if turn["status"] == "accepted":
                        if not verify_chat_blocks(turn):
                            turn = {"status": "rejected", "content": "The response did not pass its evidence checks. Results are withheld.", "mode": "local"}
                        else:
                            st.session_state.analysis = {"signature": scope_signature, "question": request,
                                "decision": turn["decision"], "response": turn["response"], "judge": turn["judge"]}
                except (OSError, ValueError, KeyError) as error:
                    turn = {"status": "error", "content": f"I couldn't complete that analysis: {error}", "mode": "local"}
                messages.append({"role": "assistant", "content": turn["content"], "turn": turn})
                del messages[:-2 * config.CHAT_MAX_TURNS]
            for index, message in enumerate(messages):
                with st.chat_message(message["role"]):
                    turn = message.get("turn", {})
                    if turn.get("notice"):
                        st.info(turn["notice"])
                    if turn.get("status") in {"error", "rejected"}:
                        st.error(message["content"])
                    elif turn.get("status") == "accepted":
                        views = turn["presentation"]
                        st.markdown(views["short_answer"])
                        if views["next_steps"]:
                            st.markdown("**What to do next**")
                            st.markdown("\n".join(f"{step}. {action}" for step, action in enumerate(views["next_steps"], 1)))
                        if turn["focus"] != "risks":
                            st.caption(views["caveat"])
                        show_detail = turn["focus"] == "detail" or (response_mode == "Detailed" and turn["focus"] != "brief")
                        with st.expander("Detailed explanation", expanded=show_detail):
                            st.markdown(views["detailed_answer"])
                        with st.expander("Copy or download answer"):
                            st.caption("Use the copy icon or download a Markdown file.")
                            st.code(views["export_markdown"], language="markdown")
                            st.download_button("Download answer", data=views["export_markdown"],
                                file_name="fmcg_answer.md", mime="text/markdown", key=f"answer_download_{index}", on_click="ignore")
                    else:
                        st.markdown(message["content"])
                    if message["role"] == "assistant":
                        st.caption("Local data assistant")
                    if index == len(messages) - 1 and turn.get("status") == "accepted":
                        response, judgement = turn["response"], turn["judge"]
                        st.success("Answer checked against the selected data.")
                        st.caption(response["evidence"]["scope"])
                        with st.expander("Charts and supporting tables", expanded=(response_mode == "Detailed" and turn["focus"] != "brief")):
                            show_visuals(response)
                        with st.expander("Execution transparency"):
                            st.write(f"Supervisor: {turn['decision']['reason']}")
                            st.write(f"Specialist: {response['specialist']}")
                            st.write(f"Tool called: {response['tool']}")
                            st.write(f"Judge result: {judgement['status']} | {judgement['method']}")
                            st.write(f"Source: {response['evidence']['source_table']}")
                            st.caption("Follow-ups rerun the current analysis; suggestions are proposals for review.")
                            st.caption("Answers and suggestions use checked local data. No external model or API is called.")
                            st.json({"supervisor": turn["decision"], "judge": judgement,
                                     "conversation_mode": turn["mode"], "context_used": turn["context_used"],
                                     "response_blocks_verified": verify_chat_blocks(turn)})
                        with st.expander("Structured tool evidence"):
                            st.json(response["evidence"])
                            st.json(turn["blocks"])
            if messages:
                def queue_followup(prompt):
                    st.session_state.pending_chat = prompt
                followup_columns = st.columns(len(config.CHAT_FOLLOWUPS))
                for column, prompt in zip(followup_columns, config.CHAT_FOLLOWUPS):
                    column.button(prompt, key="followup_" + prompt, on_click=queue_followup, args=(prompt,))

        with trace_panel, st.container(border=True):
            latest = next((m["turn"] for m in reversed(messages) if m.get("turn", {}).get("status") == "accepted"), None)
            transparency(latest)
    for workspace, title, prompt, label in [
        (customers_tab, "Customer Intelligence", "Show customer segments", "Explore customer segments"),
        (forecasts_tab, "Revenue Forecasts", None, "View forecast"),
    ]:
        with workspace:
            st.subheader(title)
            st.caption("Explore your validated data and supporting evidence.")
            if prompt is None:
                category = st.text_input("Category to forecast", value="milk")
                prompt = f"Forecast {category} for next month"
            if st.button(label, type="primary"):
                with st.spinner("Checking the data..."):
                    workspace_turn = run_chat_turn(prompt, data,
                        lambda: cached_products(PRODUCT_LOOKUP_FILE, product_signature), start_week, end_week, None)
                st.session_state["workspace_" + title] = {"signature": scope_signature, "prompt": prompt, "turn": workspace_turn}
            saved = st.session_state.get("workspace_" + title)
            if saved and saved["signature"] == scope_signature and saved["prompt"] == prompt:
                workspace_turn = saved["turn"]
                if workspace_turn["status"] == "accepted" and verify_chat_blocks(workspace_turn):
                    st.markdown(workspace_turn["presentation"]["short_answer"])
                    show_visuals(workspace_turn["response"])
                else:
                    st.info(workspace_turn["content"])
            else:
                st.info("Open the analysis to review results and their supporting evidence.")
    with st.expander("KPI source, scope, and validation"):
        st.write(result["scope"])
        st.write(f"Source: {result['source_table']}")
        st.write(result["revenue_definition"])
        st.caption("Flags may overlap. Unusual records are retained; flags do not establish that records are errors.")
        st.dataframe(pd.DataFrame([{"Flag": key.replace('_', ' '), "Count": value} for key, value in result["anomalies"].items()]), hide_index=True)
        st.caption("Checked: required columns, nonempty data, missing values, numeric types, finite values, and integer day/week/ID fields. Source fingerprints, master preparation and accepted core_consumables_v1 scope passed validation. Final report/business usefulness review remains pending.")
except ScopeNotConfiguredError as error:
    st.session_state.pop("analysis", None)
    st.session_state.messages = []
    st.warning("Data preparation passed. Exact FMCG scope definitions are still pending.")
    st.write(str(error))
    st.caption("The guide gives exclusion counts but omits the exact names. No business KPIs are calculated while IN_SCOPE is unknown.")
    show_scope_selection()
    for filename, label in [("department_scope_audit.csv", "Download department scope audit"), ("commodity_scope_audit.csv", "Download commodity scope audit"), ("drug_gm_scope_audit.csv", "Download DRUG GM scope audit")]:
        audit_path = OUTPUTS_DIR / filename
        if audit_path.is_file():
            st.download_button(label, audit_path.read_bytes(), file_name=filename, mime="text/csv")
except (OSError, ValueError, KeyError) as error:
    st.session_state.pop("analysis", None)
    st.session_state.messages = []
    st.session_state.pop("chat_signature", None)
    st.error(f"Unable to calculate KPIs: {error}")
    st.info("Check the transaction file and selected week range. No rows are silently removed to resolve errors.")











