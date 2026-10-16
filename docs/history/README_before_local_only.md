# FMCG Product Intelligence System

A local Streamlit prototype for an M.Tech Data Science project, using actual dunnhumby retail point-of-sale data. Revenue is SALES_VALUE in USD.

## Run

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Open http://127.0.0.1:8501 and type a question in the chat input. Ask follow-ups for explanations and practical suggestions; the Example questions panel also provides demos. The scope-selection blocker has been resolved: the user explicitly accepted the new core_consumables_v1 scope and its active master and aggregates passed validation.

Current Python is 3.14 provisionally. The target remains Python 3.11; installation previously failed its integrity check. Dependencies are in requirements.txt.

## Active scope and reproduced KPIs

The accepted new scope excludes 26 departments, 16 global commodities and 50 selected DRUG GM commodities. Exact names are in src/config.py, with the proposal's reasons in outputs/proposed_scope/exclusion_rationale.csv. This is a new documented boundary, not recovery of the missing historical lists from the guide. User acceptance is recorded in outputs/scope_application.json.

Analysis uses IN_SCOPE=True and weeks 19-102, including partial week 102 for KPI/customer work. Weekly forecasting uses complete weeks 19-101.

| Reproduced metric | Value |
| --- | --- |
| Revenue | $6,237,807.19 |
| Distinct baskets | 218,960 |
| Distinct households | 2,492 |
| Average basket value | $28.49 |

Source: outputs/kpi_summary.json; independent validation: outputs/aggregate_validation.json. These values differ from the earlier guide because the scope is different. Review 3 field mapping has not been performed; no Review 3 document has been supplied.

## Working local flow

Chat question or follow-up -> conversational route -> Supervisor and one of three specialists -> validated Python tool -> deterministic evidence Judge -> checked answer and proposed next steps, with charts/tables and transparency.

Supported demo questions:

- What are the sales KPIs?
- Show weekly sales trend
- Show top products
- Show customer segments
- Show category intelligence (full approved window)
- Investigate sales in week 92 (full approved window)
- Which products should we promote next month? (two category rankings)
- Forecast milk demand for next month

Extra filters and multi-part questions are rejected. Set week scope in the sidebar. Source/scope changes invalidate previous answers.

Analytics remain local deterministic modules. An optional Gemini adapter is prepared for supported routing and checked response selection; real cloud chat is unverified. Google ADK and GCP deployment are pending. The Judge verifies routing, numeric claims, fixed answer templates and internal evidence consistency. It does not independently audit raw data or assign business-value scores. Rejected answers are withheld; no automatic retry is implemented.

## Analytics limits

- Top products shows PRODUCT_ID values by revenue. Category intelligence separately ranks the top 100 commodities by a documented composite score. All scored promotion comparisons are currently unsupported by coverage/comparator guards, so the promotion term is neutral; five measured components distinguish categories.
- Full-window customer segmentation uses validated saved StandardScaler/K-Means models on log1p RFM features. Candidate k=2..10; selection requires minimum 5% cluster share and mean four-seed initialization ARI >=0.80, then maximizes sampled silhouette. Shorter-window queries are labelled exploratory refits. Profiles, affinity and descriptive demographic coverage are saved; business usefulness review and household-query routing remain pending.
- Full-window forecasting uses four saved direct gradient-boosting models, compared chronologically against naive, seasonal naive and moving average. Earlier validation selects gradient boosting for horizons 1-2 and seasonal naive for 3-4. Selected subperiods remain explicitly labelled moving-average baselines. Milk maps to FLUID MILK PRODUCTS. Four dataset weeks are a month proxy and may overlap the partial last source week.
- Calendar dates use the guide's synthetic anchor, not verified transaction dates. IS_WEIGHTED remains unknown and physical unit-price interpretation is unverified. Revenue forecasting avoids treating QUANTITY as reliable unit demand.
- Mixed-category scope tradeoffs and retained-category review notes are in data_decisions.md and outputs/proposed_scope/scope_proposal.json.

## Reproduce and validate

```powershell
.\.venv\Scripts\python.exe src/inspect_tables.py
.\.venv\Scripts\python.exe src/build_master.py
.\.venv\Scripts\python.exe src/validate_master.py
.\.venv\Scripts\python.exe src/build_aggregates.py
.\.venv\Scripts\python.exe src/validate_aggregates.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts/validate_real_data.py
```

Raw files are preserved. The master retains 2,581,333 lines and separately records the 14,399 removed quantity=0 AND sales=0 lines with source-row provenance. Other unusual records are flagged. Daily, full-week and analysis-window totals use distinct validation benchmarks; commodity distinct baskets/households are not additive.

The isolated pre-acceptance scenario remains in outputs/proposed_scope/ for provenance. Its original scenario status is historical and does not describe current active readiness. New scope proposals must still be reviewed before application. The scope-selection UI appears only if the active configuration becomes unresolved.

## Next work

Week-92 investigation, consolidated ML evaluation and processed-schema freeze are complete. The cloud CLI and SDK are installed; actual project identity and ADC sign-in are needed next. See docs/cloud_setup.md. The two recommendation rankings and trained forecasting are technically validated; human review remains pending. Category score arithmetic and weight sensitivity are validated; human usefulness review and supported promotion comparisons remain open. Saved RFM/segmentation artifacts and initialization-stability validation are now complete; business usefulness review remains pending. Complete decomposition/household tools, ADK/Gemini integration, actual cloud deployment and final report evaluation. The current system is ready for a local analytics demonstration; it is not the final publicly deployed project.


## Saved RFM and segmentation

```powershell
.\.venv\Scripts\python.exe src/build_segments.py
.\.venv\Scripts\python.exe src/validate_segments.py
```

The stage reads validated household_summary and the approved master. It writes household_rfm, clustering_features, household_clusters, household_segments, segment_profiles, segment_product_affinity and segment_demographic_profiles Parquet files, plus models/scaler.pkl and models/kmeans_model.pkl. Models and artifacts are fingerprinted; changing scope, source, model settings or the scikit-learn environment prevents stale models from being served.

Actual results: 2,492 households; selected k=2; sampled silhouette=0.398556; mean initialization ARI=1.0000 across seeds 42, 7, 21 and 84. Production seed remains 42; alternative seeds are explicitly documented stress tests. Segments contain 1,355 and 1,137 households. The sampled silhouette for k=4 is 0.316172, so four to six groups were not forced. This is a technical selection, not proof of natural customer types or final human business approval.

Scores use average percentile ranks with ties kept equal; R is reversed. F and M are baskets and revenue per week observed. Scores define a readable rule baseline; clustering uses continuous features rather than scores. Rule-baseline ARI is agreement, not accuracy. Late-entry flags use first retained source transaction, not a verified enrollment date. Demographics describe covered households only and are not model inputs. Affinity is the segment category-revenue share divided by overall category-revenue share; zero denominators remain undefined.

Evidence: outputs/segmentation_build_report.json, outputs/segmentation_validation.json, outputs/clustering_evaluation.csv, outputs/clustering_stability.csv and outputs/rfm_cluster_comparison.csv. Open outputs/clustering_diagnostics.html for standalone elbow, silhouette, stability and PCA plots.

Initialization agreement does not establish temporal robustness or business usefulness. Model reload reproduced every saved household assignment. Single-household inference is available through src.segmentation.assign_segment; natural-language household enquiry is a later tool/routing step.


## Category intelligence (Day 6 technical stage)

```powershell
.\.venv\Scripts\python.exe src/prepare_promotions.py
.\.venv\Scripts\python.exe src/validate_promotions.py
.\.venv\Scripts\python.exe src/build_product_scores.py
.\.venv\Scripts\python.exe src/validate_product_scores.py
```

Select **Show category intelligence** and keep weeks **19-102** in the sidebar. Saved scores cover the full approved snapshot; subperiod queries are rejected. The existing SKU revenue ranking remains available as Show top products.

The index uses percentile ranks among the top 100 commodities by revenue: revenue share 25%, growth 15%, household penetration 20%, repeat-purchase rate 15%, revenue per buyer 15%, promotion association 10%. Weights are analyst choices, not learned estimates. Buyers/repeat/value use weeks 19-102; growth and promotion diagnostics use 83 complete weeks (19-101). Growth compares mean weekly revenue in 41 versus 42 weeks. Synthetic-calendar YoY pairs six complete overlapping months; it is a diagnostic rather than verified holiday/seasonal adjustment.

Promotion preparation scans all 36,786,524 source rows in chunks. It matches 435,199 of 2,013,580 observed sold product/store/week keys (21.61% coverage). Multiple source placements are combined once per sales key. Missing records remain unknown. With/without display/mailer diagnostics and a separate higher/lower exposure comparison use coverage, support, weekly-revenue stability and shrinkage guards. **No scored category meets the promotion comparison guards.** Its normalized promotion component is 0.5 (five points at the default weight), so it does not distinguish categories. It is not evidence of zero effect. See data_decisions.md for the exact rules and tradeoffs.

Across 100 seeded relative weight perturbations of ±20%, minimum full-ranking Spearman is 0.991416; minimum baseline-top-20 Spearman is 0.966808; minimum top-20 retention is 90%. Arithmetic and these engineering stability checks pass. They do not establish business value, causal effects or stability over time.

Outputs: data/processed/product_scores.parquet, category_components.parquet, promo_lift.parquet, promo_category_weekly.parquet and promotion_sales_keys.parquet. Evidence: outputs/category_build_report.json, category_validation.json, promotion_build_report.json and promotion_validation.json. Open outputs/category_diagnostics.html for the standalone chart, outputs/category_findings.md for findings, and category_weight_sensitivity.csv / category_rank_ranges.csv for reproducible sensitivity details.

Current verification: 81 unit tests and all eight real-data tool/Judge and Streamlit flows passed. Saved scores reject changed source, policy, settings, preparation or artifact fingerprints. Local demo readiness is true; final public launch remains false.


## Trained forecasting (Days 7-8 technical stage)

```powershell
.\.venv\Scripts\python.exe src/build_forecasts.py
.\.venv\Scripts\python.exe src/validate_forecasts.py
```

Select **Forecast milk demand for next month**, keeping the full approved weeks **19-102**. The prediction targets revenue in USD and starts after complete dataset week 101. Other exact forecastable commodity names are supported by the same question pattern. Subperiod queries use the clearly labelled exploratory baseline.

The saved package contains four direct HistGradientBoostingRegressor models. Its 201-category cohort is determined from complete weeks 19-71 before any validation outcomes. Three expanding validation blocks are 72-77, 78-83 and 84-89. Hyperparameters and global serving methods per horizon are chosen only on these blocks. Frozen evaluation models train on labels through week 89; the final test target block is 90-101. Production models refit on observed labels through complete week 101.

At horizons 1/2/3/4, the test contains 12/11/10/9 rolling origins per category. Comparisons within each horizon use identical categories, origins and targets. Four-week totals use nine common origins; overlapping totals are not independent uncertainty samples.

| Horizon | Gradient boosting WAPE | Naive | Seasonal naive | Moving average | Served method |
| --- | --- | --- | --- | --- | --- |
| 1 | 16.05% | 21.35% | 16.49% | 18.03% | Gradient boosting |
| 2 | 16.30% | 22.16% | 16.64% | 18.27% | Gradient boosting |
| 3 | 17.29% | 24.26% | 16.76% | 18.94% | Seasonal naive (52 weeks) |
| 4 | 16.80% | 22.11% | 16.03% | 18.51% | Seasonal naive (52 weeks) |

| Method | Four-week-total WAPE |
| --- | --- |
| Gradient boosting | 10.44% |
| Naive | 17.83% |
| Seasonal naive (52 weeks) | 10.16% |
| Four-week moving average (fixed origin) | 12.34% |
| Validation-selected forecast | 9.07% |

These are pooled held-out WAPE results, not future accuracy guarantees. Gradient boosting beats all three baselines for 87/81/82/71 of the 201 categories at horizons 1/2/3/4. It does not consistently beat seasonal naive at longer horizons, and seasonal naive has lower overall RMSE at all four horizons. The dashboard shows the trained model and the validation-selected forecast rather than concealing losing comparisons.

Features include commodity category, origin-only scaled revenue lags/rolling statistics, line-level loyalty-discount share, covered observed-sales promotion shares with missingness, and synthetic cyclic calendar positions. Missing shares stay unknown; there are no future promotion inputs, holiday flags or lag-52 model features. Seasonal naive alone uses the 52-week offset. No shuffled split, random early-stopping holdout or production forecast accuracy claim is used.

Exact-commodity inference is available through `src.forecast_access.predict_next_weeks(commodity, h)`, for h=1..4. Saved model/source/configuration/library/artifact fingerprints must pass before inference. Week 92 remains in training/evaluation; its errors are reported without asserting a cause.

Files: models/forecast_model.pkl and forecast_evaluation_models.pkl; data/processed/forecast_panel, forecast_covariates, forecast_backtest, forecast_validation_predictions, forecast_next_weeks and forecast_total_backtest Parquets. Reports: outputs/forecast_validation.json, forecast_build_report.json, forecast_tuning.csv, forecast_metrics_overall.csv, forecast_metrics_by_category.csv, forecast_improvement.csv, forecast_total_metrics.csv, forecast_error_by_week.csv and forecast_error_by_volatility.csv. Standalone chart: outputs/forecast_diagnostics.html. Findings: outputs/forecast_findings.md.

81 unit tests and all eight actual-data tool/Judge and Streamlit flows pass. Independent validation refits every tuning candidate, freezes test models at the stated cutoff, checks past-only features and reproduces every saved future prediction. Separate recommendation rankings are now implemented; business usefulness review, cloud integration and final public launch remain pending.


## Two recommendation rankings (Day 9 technical stage, 13 October 2026)

```powershell
.\.venv\Scripts\python.exe src/build_recommendations.py
.\.venv\Scripts\python.exe src/validate_recommendations.py
```

Choose **Which products should we promote next month?** using the full weeks **19-102**. The app shows two top-ten category lists. Both cover 100 scored categories; one category appears in both top tens: **DIAPERS & DISPOSABLES**. Each list retains its own evidence and scores; no automatic winner is chosen.

Forecast ranking: 60% percentile-ranked forecast growth plus 40% category intelligence score / 100. Growth compares selected forecast revenue for weeks 102-105 against observed complete weeks 98-101. Segment ranking: 60% percentile-ranked target-group affinity plus 40% percentile-ranked group momentum (98-101 versus 94-97). Target groups require a median observed revenue/week index >=1.25; actual group 1 contains 1,355 households and 84.4585% of window revenue. The rule measures observed spending, not profit or customer lifetime value.

The saved table retains ineligible rows with explicit reasons and null scores/ranks. Zero denominators remain unknown. Target support requires 50 buyers. Promote labels require a top-ten rank and growth/momentum >=5%; the segment label also needs absolute affinity >=1.05. A decline below -5% is review; forecast total WAPE above 25% or unknown is also review. Remaining eligible rows are maintain. Labels are provisional test hypotheses; **every row remains review_required**. No promotion effect, incremental revenue, ROI or recommendation accuracy is estimated. Promotion associations are unavailable for the whole cohort.

Actual provisional labels across all rows: forecast 7 promote / 40 maintain / 53 review; segment 0 promote / 80 maintain / 20 review. These totals do not establish validated campaign actions. Both top-ten lists still need Megh's human plausibility review.

Snapshot/category/segment evidence includes partial source week 102. Forecast origin is the last complete week 101, so target weeks 102-105 overlap partial week 102. This is a current-snapshot proposal, not a historical point-in-time recommendation backtest or four entirely future weeks.

Files: data/processed/recommendations.parquet, recommendation_category_evidence.parquet and recommendation_segment_weekly.parquet. Reports: outputs/recommendation_build_report.json, recommendation_validation.json, recommendation_top10.csv and recommendation_findings.md. Standalone comparison chart: outputs/recommendation_diagnostics.html. All source/configuration/upstream/artifact fingerprints must match; subperiod requests are rejected.

81 unit tests, eight actual-data tool/Judge flows and eight Streamlit flows passed. Independent validation recomputes forecast totals, matched baseline errors, pooled group affinity/buyers/momentum, weighted scores, labels and overlap directly from approved processed sources. The deterministic Judge checks both lists; business arbitration is a later stage. Week-92 diagnosis and ML evaluation pass; next is actual cloud-access proof, using docs/cloud_setup.md. Final public launch remains pending.


## Week-92 diagnosis and ML evaluation (Day 10, 13 October 2026)

Choose **Investigate sales in week 92** with full weeks **19-102**. Revenue $94,551.58 versus surrounding-week mean $76,558.11 (+23.50%). Changes span 75/115 eligible stores and 8/9 major departments. Records are retained; cause remains unverified.

```powershell
.\.venv\Scripts\python.exe src/build_week_diagnosis.py
.\.venv\Scripts\python.exe src/validate_week_diagnosis.py
.\.venv\Scripts\python.exe src/build_ml_evaluation.py
.\.venv\Scripts\python.exe scripts/validate_ml_evaluation.py
```

[evaluation_ml.md](outputs/evaluation_ml.md) consolidates actual segmentation, category, forecasting, recommendations and diagnosis results with baselines and limitations. [eda_findings.md](outputs/eda_findings.md) summarizes supported findings. All **28 processed Parquet schemas**, row counts and SHA256s are frozen in outputs/processed_schema_manifest.json; intentional changes require fresh generation/validation. Independent Day-10 validators passed. Build reports retain BUILT_REQUIRES_VALIDATION; matching separate validators establish PASS.

Google CLI 588.0.0 and google-genai==2.30.0 are installed; archive SHA256, executable version and pip dependencies passed checks. [Cloud setup instructions](docs/cloud_setup.md) provide account steps and a fixed greeting test. Project ID and ADC sign-in are missing. No actual cloud call has run; ADK and deployment are pending.

81 unit tests, eight processed-data tool/Judge flows and eight Streamlit flows passed, including strict JSON diagnosis evidence, cause-claim rejection, subset guards and stale-answer invalidation. Local demo ready; final public launch false.


## Conversational dashboard — 13 October 2026

Type a question in the chat input. Examples:

- How are sales doing?
- What are our best sellers?
- How can we improve sales?
- Forecast milk for next month
- Why did sales spike in week 92?

Answers include proposed next steps and supporting charts/tables. Ask **Why?**, **What should I do next?**, or **What are the limitations?** to continue the last successful analysis, retaining its commodity for forecasts. The buttons submit real turns. Example questions remain available in a collapsed panel.

Conversation lives in the current browser session, retains at most 24 complete turns, and resets when the data or sidebar scope changes. New conversation clears it. Unknown requests are clarified; they never become invented analytics. Follow-ups rerun tools and evidence checks rather than reuse stale figures. Unsupported filters and multiple analyses remain blocked.

The **local assistant** works now with conversational aliases and evidence-derived summaries/actions. It is not a connected GPT model or unrestricted language model. Actions are review proposals, not automatic campaigns or guaranteed results. The existing Supervisor, three specialists and deterministic Judge still calculate and check the analytics.

An optional **Use connected Gemini** toggle is available after the [cloud setup](docs/cloud_setup.md) has a real matching model-access PASS and local credentials/project configuration. The adapter interprets supported requests into checked route enums and selects checked response paragraphs; it does not produce unrestricted prose or new numbers. It sends the submitted question, previous route and checked aggregate paragraphs, not raw retail rows or household histories. It is off by default. Model errors or invalid selections fall back to a visibly labelled local response; credentials/raw authentication exceptions are not displayed.

81 unit tests, all eight processed-data tool/Judge and dashboard demo flows, and nine natural chat flows passed, plus rerun, unknown-request, button, retention, reset and source/scope checks. Report: outputs/chat_validation.json. The live cloud path has only SDK-contract/stub verification; actual cloud chat remains unverified. ADK/public deployment remain pending.


## Short answers, details and next steps — 13 October 2026

Each successful chat answer now shows a concise summary and **What to do next**. Expand **Detailed explanation** for the full reasoning, scope and caveats. Forecast details retain the actual baseline error comparison, including methods that perform better than the trained model.

The sidebar **Answer length** preference defaults to **Short + details**; **Detailed** opens explanations and charts. A typed **Give me a short answer** or **Explain in detail** follows the last successful analysis and its commodity. Short requests keep details collapsed; explicit detailed requests open them. Changing the preference does not rerun analytics or duplicate messages.

**Copy or download answer** contains a native copy control and a Markdown download of the short answer, full details, next steps and scope. Charts stay collapsed by default for concise reading. Brief and detailed text are derived from the same checked evidence; edited figures, actions, caveats or download contents fail verification.

81 unit tests, eight actual-data analytics/dashboard flows and nine natural chat flows passed, including answer formats, follow-ups, preference changes and export contents. Evidence: outputs/chat_validation.json. Existing data, models, scope and cloud-access gates are unchanged.
