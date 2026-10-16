# FMCG Product Intelligence System

A local Streamlit dashboard and chat assistant for an M.Tech Data Science project, using validated dunnhumby point-of-sale data. The active workflow is **local-only in VS Code**, following the user's decision on 13 October 2026. Cloud accounts, GCP, deployment and external model APIs are not requirements.

## Run entirely in VS Code

1. Open this project folder in VS Code.
2. Open **Run and Debug** and select **FMCG: Local dashboard in VS Code**.
3. Press **F5**. The local server starts in the integrated terminal and its URL opens in VS Code's integrated browser.

The configuration uses the existing .venv interpreter. Python and Python Debugger extensions are already installed on this machine. Press **Shift+F5** to stop the debug session. If you previously started another server on port 8501, stop that server's terminal first.

The editor launch behavior uses the installed server-ready extension's openIntegratedBrowser action. VS Code also documents the [integrated browser](https://code.visualstudio.com/docs/debugtest/integrated-browser) and [Python launch configuration](https://code.visualstudio.com/docs/python/debugging). No external browser is launched by the app.

[Detailed local setup instructions](docs/local_setup.md) include terminal tasks and troubleshooting. The earlier cloud guide is retired; archived project notes are under docs/history/.

## Chat and dashboard features

- Sales KPIs, weekly trends and leading products.
- Saved customer segments and category scores.
- Week-92 department/store diagnosis.
- Saved revenue forecasts with matched baseline comparisons.
- Separate forecast-based and customer-group-based promotion priorities.
- Short answers, expandable detailed explanations and clear next steps.
- Remembered why/short/detail/next-step follow-ups.
- Charts, evidence tables, native copy controls and Markdown downloads.

Try **How are sales doing?**, **How can we improve sales?** or **Forecast milk for next month**. Then ask **Give me a short answer**, **Explain in detail** or **What should I do next?**.

Chat uses supported local question patterns and checked evidence-derived response paragraphs. Unknown requests are clarified. Extra filters and multiple tasks remain unsupported; set dataset week bounds in the sidebar. Saved scores/recommendations/diagnosis require the full approved window. Conversation remains in the current session, holds up to 24 complete turns, and resets when data or scope changes.

Analytics run through the Supervisor, three local specialist modules, Python tools and deterministic evidence Judge. No external model is called. Suggestions are proposals for review, not approved campaigns or guaranteed outcomes.

## Active scope and verified results

The user accepted core_consumables_v1: 26 department exclusions, 16 global commodity exclusions and 50 selected DRUG GM exclusions, defined in src/config.py. This is a documented new scope; the guide's missing historical lists were not reconstructed. Application evidence: outputs/scope_application.json.

Analysis uses IN_SCOPE=True and weeks 19-102, including partial week 102 for KPI/customer work. Forecasting uses complete weeks 19-101.

| Metric | Actual value |
| --- | ---: |
| Revenue (USD) | $6,237,807.19 |
| Distinct baskets | 218,960 |
| Households | 2,492 |
| Average basket value | $28.49 |

Only quantity=0 AND sales=0 preparation rows were removed, with separate provenance. Other flagged records remain. Raw files are preserved. Category distinct basket/household counts are not additive.

Saved clustering selected two groups, silhouette 0.398556 and mean four-seed initialization ARI 1.0000. This does not establish temporal stability or business usefulness. Category scoring covers 100 priorities; no scored category has supported promotion-association evidence. Missing association is neutral, not zero effect.

Forecasting evaluates 201 categories chronologically. Validation selects gradient boosting for horizons 1-2 and seasonal naive for 3-4. Four-week held-out WAPE is 9.0693% for the selected pipeline, 10.4412% for gradient boosting alone and 10.1616% for seasonal naive. Baselines are retained in the dashboard; there is no uniform superiority or future-accuracy guarantee.

Week 92 revenue is 23.50% above the mean of complete weeks 90/91/93/94. Increases span stores/departments; records are retained and cause remains unverified. Recommendations are current-snapshot priorities, not causal campaign evidence or point-in-time recommendation backtests.

Actual results and limitations: [ML evaluation](outputs/evaluation_ml.md), [analytics findings](outputs/eda_findings.md) and [data decisions](data_decisions.md). All 28 processed Parquet schemas/types/row counts/content hashes are frozen in outputs/processed_schema_manifest.json. Dated evaluation reports mentioning the old cloud plan are historical; the local-only decision supersedes those next-step requirements.

## Verification and remaining research

87 unit tests, eight actual tool/Judge/dashboard flows and nine natural chat flows passed. The exact local launcher was started and its health endpoint returned HTTP 200. Its server-ready URL pattern and installed integrated-browser action were checked; automated interaction with VS Code's F5 UI itself was not performed.

Run **Tasks: Run Task** in VS Code to select **FMCG: Run tests**, **FMCG: Validate dashboard on real data** or **FMCG: Check local setup**. Results are recorded in outputs/chat_validation.json, outputs/vscode_local_validation.json and outputs/local_readiness.json.

Current Python is 3.14.4; the original Python 3.11 portability target remains unfulfilled after its installer integrity failure. The current local app is tested and runnable. Human usefulness/temporal robustness, household/decomposition tools, final academic evaluation and Review 3 mapping remain research work. Calendar dates and physical units are unverified. GCP, ADK cloud integration and public deployment are excluded from the requested app scope.

Only requirements.txt is needed for local dependencies. Existing retired cloud files are preserved for provenance, excluded from the app workflow and blocked by LOCAL_ONLY_MODE. No cloud download, authentication, resource provisioning or model call is performed.

## Review III presentation and exact blank values — 13 October 2026

The supplied 19-slide Review III PPT was mapped to the actual local implementation. A filled copy resolves all 36 numeric/text blank slots and corrects unsupported claims about GCP, BigQuery ML, ARIMA_PLUS, four trained clusters, eight-week intervals and 100% completion. The original file remains unchanged.

- [Filled presentation](outputs/review3/FMCG_Review_III_Verified_Local.pptx)
- [Slide-wise values and assumptions](outputs/review3/blank_values.md)
- [Copyable CSV values](outputs/review3/blank_values.csv)
- [Revised slide text preview](outputs/review3/revised_slide_text.md)

New descriptive values: top departments GROCERY / DRUG GM / PRODUCE contribute 76.78% of window revenue; discounted-sales share is 49.76%; mean baskets/household is 87.87; the complete-week peak is 92. These share/mean calculations use the explicit approved snapshot and definitions in the report.

The trained K-Means model remains k=2. Four-group slide rows now show the separately saved RFM rule baseline (512 / 980 / 814 / 186 households) with its actual rule names, not invented Champions/Loyal/At-Risk cluster names. Mean spend is selected-window revenue per household. No model was retrained to force four clusters.

The forecasting slide uses correctly labelled matched H1 gradient-boosting MAPE/RMSE, not fabricated ARIMA values. Future coupon/cross-sell, longer horizons/intervals and multilingual/alert examples are explicitly labelled assumptions; their effects/performance are not measured.

Use **Tasks: Run Task → FMCG: Build Review III presentation**, then **FMCG: Validate Review III presentation**. Source/code paths are configured locally; an alternate source path can be supplied with --presentation. Independent validation recomputes the numeric values and checks the PPTX package, original preservation and remaining placeholders. PowerPoint-native rendering has not been performed; inspect the presentation visually before presenting. Business usefulness and academic review remain open.