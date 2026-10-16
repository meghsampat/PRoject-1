# Data decisions

Recorded 12 October 2026. Project days describe working sessions, not calendar dates.

## Current reproducible state

The supplied guide describes Days 1-4 as DONE in an earlier project. Those earlier scripts, scope definitions, and processed outputs were absent from this repository. We did not inherit their results or copy the guide's $6.57M figure. The current repository has reproduced source inspection and the preparation steps below. The user has now accepted a new explicit core-consumables scope. Active master and Day 3 aggregate calculations are rebuilt and validated. The earlier pending-scope sections below are a chronological record, superseded by the acceptance record at the end. Weighted-product classification and full EDA/model work remain pending.

## Confirmed preparation decisions

- Raw CSV files are preserved. Source inspection scans all eight tables in chunks and records actual row counts, null counts and SHA-256 hashes in outputs/source_inspection.json.
- Only records with QUANTITY=0 AND SALES_VALUE=0 are removed from the master. They are retained separately in data/processed/removed_zero_zero_lines.parquet with SOURCE_ROW_ID provenance. 14,399 lines meet this rule.
- The prepared master contains 2,581,333 lines. Its unscoped SALES_VALUE sum reconciles to raw revenue; no final FMCG revenue is claimed.
- Product metadata is joined many-to-one on PRODUCT_ID. Duplicate or missing lookup entries stop the build; no unmatched sales lines are silently dropped. Join count and revenue are checked.
- Synthetic calendar: DAY 1 = 2015-12-30 (Wednesday), DAY 6 is Monday. Calendar-derived week numbers match every source line. Full weeks are 2-101; edge weeks 1 and 102 are partial. These dates are not verified purchase dates and do not support real holiday attribution.
- ANALYSIS_START_WEEK=19 follows the supplied guide. The end is the last observed week for KPI/customer work; weekly forecasting uses full weeks. Dates and window constants live in src/config.py.
- 67 zero-quantity/nonzero-sales lines are retained and flagged. Negative quantity/sales and positive discount values are also flagged. Free items and loyalty/coupon flags are explicit. Discounts are not added to or subtracted from SALES_VALUE for revenue.
- Demographics cover 801 retained households (32.04%). The lookup is saved separately; its limited coverage does not remove sales or customers.
- IS_WEIGHTED is unknown because no verified classification rule was provided. Integer QUANTITY and product size strings do not prove a product is unweighted. UNIT_PRICE_PAID is populated only for positive-quantity in-scope lines once scope is known, and its physical-unit interpretation remains unverified.
- New analysis uses validated processed files, IN_SCOPE=True and the configured window. The Streamlit app now reads the accepted in-scope week-19 data and displays the KPI/question interface. The pending-scope gate remains for any future unresolved configuration.
- Current segmentation candidate selection now uses a minimum 5% cluster share to match the new guide. Clusters remain exploratory; named segments, saved models, stability checks and final business validation are not complete.

## Missing definitions — do not guess

The guide states counts but omits names for:

1. The 21 excluded departments.
2. The 16 excluded commodities.
3. The 32 DRUG GM review commodities, plus whether those categories should be kept or excluded.

The actual product lookup contains 91 DRUG GM commodities. A blanket DRUG GM exclusion would therefore be a new decision, not reproduction of the documented 32-category rule. Until exact definitions are supplied, config uses None and IN_SCOPE is nullable/unknown for every prepared row. None is distinct from an explicit empty exclusion list.

The weighted-product classification is also pending. No fabricated weighted flags are inserted.

Scope audits enumerate actual departments and department/commodity pairs with unscoped counts and revenue:

- outputs/department_scope_audit.csv
- outputs/commodity_scope_audit.csv
- outputs/drug_gm_scope_audit.csv

## Aggregate design and correct benchmarks

The aggregate code is implemented and tested with synthetic fixtures, but real scoped execution is blocked:

| Output | Benchmark |
| --- | --- |
| commodity_daily | All IN_SCOPE rows, including partial edge weeks; zero-filled commodity/day grid |
| commodity_weekly | IN_SCOPE rows in full observed weeks only; zero-filled commodity/week grid |
| household_summary | IN_SCOPE rows in the configured week-19 window |
| kpi_summary.json | Same in-scope analysis window; partial terminal week retained |

Revenue must reconcile to each appropriate benchmark. Commodity basket/household counts are not additive across categories. Forecastable means positive weekly revenue in at least 90% of full analysis-window weeks. Household observed weeks run from first in-window purchase through the master's last selected day; this is observed participation, not known customer tenure.

## Validation and next action

outputs/master_validation.json records independent raw-line reconciliation, source/artifact hashes, lookup equality, calendar/week checks, flags and the unknown-scope gate. Current status is PASS for preparation, scope_ready=false. No commodity aggregates, kpi_summary.json, final metrics, or Review 3 fields were generated.

Next: supply exact scope definitions in src/config.py, rebuild and validate the master, build and validate real aggregate tables, rerun processed-data/UI validation, then proceed to saved RFM and segmentation models. Record any changed decisions here.

## Scope selection workflow

The pending-scope screen now offers searchable selectors populated from the processed product lookup, with the guide's counts shown as advisory references and actual audit tables for review. No exclusions are preselected. Users explicitly review their choices and select a DRUG GM keep/exclude decision before generating a configuration block. Empty lists mean a deliberate choice to exclude nothing; they are not inferred from missing definitions.

Generated configurations are drafts. They neither modify config.py nor rebuild data. The user can paste the block into this chat for application, or replace the four existing assignments in src/config.py and run the preparation/aggregate commands. Changing selections invalidates the displayed draft. Exact historical scope reproduction is still pending.

## Proposed core-consumables scope scenario

A new explicit proposal was prepared to help resolve the scope blocker. It is NOT a reconstruction of the missing historical names and has not been applied. The proposal excludes 26 departments, 16 global commodities and 50 selected DRUG GM commodities. All names were checked against the actual processed product lookup; every exclusion has a reason in outputs/proposed_scope/exclusion_rationale.csv.

The broad food/toiletries/health-consumables framing uses NIQ's official FMCG overview: https://nielseniq.com/global/en/insights/analysis/2022/what-is-the-difference-between-fmcg-and-cpg/ . Exact project exclusions are analyst judgments, not a taxonomy supplied by NIQ. Utilities, tobacco, services, durable merchandise and broadly unclassified labels are outside this proposed boundary. Some mixed labels are excluded conservatively; others such as cleaning aids, baby-care accessories and home-health products are retained with explicit SKU-level review limitations. Alcoholic beverages and household/pet consumables are retained as deliberate study choices.

scripts/prepare_scope_proposal.py generated isolated real-data scenario aggregates, KPI evidence and all five demo tool results under outputs/proposed_scope/. Daily/full-week/window totals and distinct-count benchmarks reconciled, all five tool/Judge consistency checks passed, and active config.py and transactions_master.parquet hashes were unchanged during scenario execution. Its status is PASS_SCENARIO_NOT_APPROVED, not final project validation. No scenario figures may be used as approved Review 3 results.

The app offers Load tested proposal for review, which populates selectors only. Fresh review is required before generating a draft; no configuration or processed files are changed. The active IN_SCOPE flag remains unknown until the user accepts exact definitions and the master is rebuilt/validated.

Two bugs found during real scenario validation were corrected: comparing boolean scope flags now accounts for pandas storage dtype, and forecast excluded_partial_weeks now contains native Python integers so strict JSON evidence can be saved.


## User acceptance and active rebuild — current state

The user explicitly selected Apply the tested new scope (Recommended) in this chat. The exact proposed core_consumables_v1 definitions were applied to EXCLUDED_DEPARTMENTS, EXCLUDED_COMMODITIES, DRUG_GM_REVIEW_COMMODITIES and DRUG_GM_POLICY in src/config.py. All other settings were preserved. The policy is now active: 26 excluded departments, 16 globally excluded commodities, 50 reviewed DRUG GM commodities excluded. This supersedes the unresolved-scope state recorded earlier; the original missing historical lists remain unrecovered.

The active master was rebuilt and independently validated with scope_ready=true. Real commodity_daily, commodity_weekly and household_summary tables and kpi_summary.json were generated. Aggregate validation passed all six revenue benchmarks, grid/key checks, global distinct counts, household rates and forecastability checks. All five processed-data tools/Judge paths and all five Streamlit result/chart/transparency paths passed; 23 unit tests passed. Scope/source changes and unsupported questions were also checked.

Under the accepted scope and weeks 19-102 (partial terminal week included), reproduced revenue is $6,237,807.19, distinct baskets 218,960, households 2,492 and average basket value $28.49. These are current real-data calculations backed by outputs/kpi_summary.json and outputs/aggregate_validation.json. They replace earlier-guide assumptions for this repository; no target metric was forced. These are not automatically inserted into Review 3, which has not been supplied.

The saved isolated proposal/scenario artifacts remain as pre-acceptance provenance; their original unapproved status is historical. Active application/rebuild evidence is in outputs/scope_application.json and current master/aggregate validation reports. The app is ready for a local demonstration, with rule-based agents and baseline forecasting. Public final-project launch, saved/stable ML models, recommendations, ADK/Gemini/GCP and weighted-product classification remain pending.

## Saved RFM / segmentation stage — 12 October 2026

Implemented and executed build_segments.py and validate_segments.py on the active approved processed-data snapshot. No raw CSVs or synthetic training data were used. Actual coverage is 2,492 households. All original observations/outliers were retained; invalid negative/missing feature values are errors rather than silently removed or clipped.

R/F/M scores use five average-percentile-rank bands, with tied values receiving identical scores. R scoring is reversed so more recent households score higher. Frequency and monetary values are rates per week observed. Ties can produce unequal band sizes; constant features are not arbitrarily split. Continuous log1p recency_days, baskets_per_week and revenue_per_week, standardized with a saved StandardScaler, are the clustering features. Household IDs, score columns and demographic attributes are not clustering inputs.

Candidate k=2..10 was evaluated with inertia, sampled silhouette, minimum cluster size, and pairwise adjusted Rand indices across four seeds (42, 7, 21, 84). Final production fit uses seed 42 and ten initializations. Extra seeds are stress tests explicitly required by the guide. Technical eligibility requires at least 5% of households in each final cluster and mean initialization ARI >=0.80; the eligible model with highest sampled silhouette is selected. The stability threshold is a documented engineering decision, not a universal statistical rule.

Actual selection: k=2, sampled silhouette 0.3985562678, mean initialization ARI 1.0. Cluster sizes are 1,355 and 1,137. k=4 silhouette is 0.3161719829; the guide's suggested four-to-six preference was not forced. First two PCA components explain 92.1718%, calculated anew rather than copying the guide. Rule baseline versus K-Means ARI is 0.2953956746; this measures partition agreement, not prediction accuracy.

Profiles include medians/means, household and revenue shares, indices versus population medians, late-panel-entry concentration, descriptive demographic coverage, provisional business names and suggested tests. Segment 1 accounts for 84.4585% of window revenue; segment 2 for 15.5415%. Names/actions are derived from explicit median thresholds (1.25 times population median for high rates; 28 days for long gaps), with unique group identifiers. They need human usefulness review; no causal campaign benefit is claimed.

Late panel entry is first retained source transaction after week 19, including out-of-scope source records, not first in-window purchase or verified enrollment. Demographics are described only within covered households and never used to fit clusters. Product affinity is category share of segment revenue divided by category share of total revenue; zero denominators are null. Totals and key coverage were independently checked.

Saved models/scaler.pkl and models/kmeans_model.pkl reload and reproduce every assignment. Independent checks also verify feature transforms, scalar moments, RFM source arithmetic, score tie/order behavior, selected-model criteria, four-seed refits, profile totals, source fingerprints and affinity arithmetic. 28 unit tests and all five actual tool/Judge/UI flows passed. The full approved window now serves the validated saved profiles; selected subperiods are explicitly labelled exploratory refits.

Initialization stability does not establish temporal/sample robustness. These are practical divisions of a customer continuum, not proven natural classes. Business usefulness review, temporal/sample checks and Review 3 field mapping remain pending. The next technical phase is category intelligence scoring with documented weights and sensitivity, followed by trained forecasting and recommendations.

Metric definitions: https://scikit-learn.org/stable/modules/generated/sklearn.metrics.silhouette_score.html and https://scikit-learn.org/stable/modules/generated/sklearn.metrics.adjusted_rand_score.html .

## Category intelligence / Day 6 technical stage — 12 October 2026

The accepted business scope remains unchanged. Analysis reads validated processed master, daily and weekly files only. New raw access is restricted to chunked causal-data preparation and its independent source validator.

Promotion source interpretation: the [dunnhumby-authored 2014 guide (public mirror)](https://github.com/Lanbig/CSC465-visualization-project/blob/master/Dataset/dunnhumby%20-%20The%20Complete%20Journey%20User%20Guide.pdf) describes product/store/week display and mailer records. The [maintainer's completejourney reference](https://bradleyboehmke.r-universe.dev/completejourney/doc/manual.html) documents zero as no display/no mailer and nonzero placement codes. Its one-year Complete Journey 2.0 sample is a different version; its counts/dates were not transferred to this project. Only code semantics were used, checked against every observed source code. The downloaded guide is local reference material, not a runtime dependency or an analysis dataset.

prepare_promotions.py scanned all 36,786,524 source rows in 250,000-row chunks. Observed approved complete-window sales keys number 2,013,580; 435,199 match promotion records (21.6132%). There are 605 matched keys with multiple source records. Some contain both zero display and an actual placement. They are combined by any nonzero display/mailer, preserving exact code-set masks and source-record counts. They contribute one vote per observed sales key, so revenue is never duplicated. Unknown/missing promotion keys remain unknown. Raw source rows are preserved. The validator independently rescanned the source and reconciled every matched flag, missing-key status, key count and category/week denominator.

promo_category_weekly shares count matched observed sold product/store/week keys, not transaction lines, revenue, all store inventory or household exposure. This conditions on realized sales and can be biased by assortment and purchase selection. It is an explicit analytic proxy, not a claim that the full assortment is known.

Promotion guard settings are analyst choices in config.py: at least 50% matched sales-key coverage and five matched keys per usable category/week; at least eight weeks in each comparator group; at least 90% positive-sales complete weeks; population weekly-revenue CV <= .75. Sample shrinkage is smaller-group weeks / (smaller-group weeks + 12). Separate with/without display, mailer and any-promotion contrasts are saved. A median split compares higher versus lower matched any-promotion share separately; this is not relabelled as with/without lift. Constant shares, sparse comparators, unstable revenue and zero comparator revenue remain undefined. No causal conclusion is allowed.

All 100 scored higher/lower promotion associations are undefined: 98 lack supported comparators, two fail stability. There are also no supported any-versus-none contrasts in this cohort. Two display-only contrasts outside it are diagnostic only. STONE FRUIT has weekly-revenue CV 1.374509 and fails the stability guard. Do not weaken these rules to reproduce the previous guide's lift figures.

category_components covers 229 commodities. product_scores selects the top 100 by weeks 19-102 revenue, with alphabetical tie resolution. Revenue share, penetration, repeat purchases and revenue/buyer use that approved window including partial terminal week. Repeat means buyers observed in >=2 distinct weeks, not multiple baskets on one day. Growth is second-half mean weekly revenue / first-half mean weekly revenue - 1 across complete weeks 19-101: 41 versus 42 weeks, avoiding unequal duration bias. Growth outside the scoring cohort is not used. YoY compares revenue/day across six paired complete synthetic-calendar months; it is a diagnostic, not real-calendar holiday or seasonality adjustment. Twelve scored categories disagree in growth sign, retained as a review flag.

Weights: revenue_share .25; growth .15; household_penetration .20; repeat_purchase_rate .15; revenue_per_buyer .15; promotion_association .10. They prioritize scale/reach (45%), retention/value (30%), recent change (15%) and a reserved guarded promotion signal (10%). They are analyst choices, not learned/optimized estimates. Some indicators are correlated, which is acknowledged rather than treated as independent evidence.

Normalize each known component among the scoring cohort by (average tied rank - 1)/(known count - 1). Constant or missing components receive normalized .5. Raw unknown values remain missing and missingness is explicit. Every scored promotion term is currently neutral, contributing five constant points; it does not distinguish categories or indicate zero effect. Score = 100 times the weighted sum. Labels mean higher composite score versus other scored category, not promote/maintain decisions. Recommendations are a later stage.

Sensitivity uses production seed 42, 100 runs, independent relative perturbations ±20% per weight, then renormalization. Minimum full-ranking Spearman .991416; median .997090. Minimum fixed-baseline-top-20 Spearman .966808; median .990515. Minimum top-20 overlap .90; median .95. Engineering gates (full-ranking minimum >=.90, top-20 overlap minimum >=.80) pass. Rank ranges and all actual perturbed weights are saved. No human business usefulness approval or temporal stability is inferred.

Independent validation reproduced direct source revenue/counts/repeat rates, unequal-length half growth, complete-month YoY, guarded promotion contrasts, percentile normalization, weighted scores, rank ordering and all perturbations. It found a sign-review flag computed before growth was disabled outside the scoring cohort; the flag is now consistent with the saved growth field and rebuilt outputs pass. Saved artifact access rejects changed source, scope, settings, preparation report, inventory or content hashes. The Supervisor/Data Science tool/Judge and dashboard now support Show category intelligence; only the full saved window 19-102 is accepted.

Verification after final code changes: 36 unit tests, six real-data tool/Judge flows, six Streamlit result/chart/transparency flows; stale answers, unsupported requests, invalid bounds and subperiod category requests checked. Reports: outputs/promotion_validation.json and outputs/category_validation.json (PASS). Descriptive category scoring is technically ready for local demo. Promotion comparisons and human usefulness review remain open. Next: chronological trained direct-horizon revenue forecasting and baseline comparison, then recommendations. ADK/GCP, Python 3.11, final public launch and Review 3 remain pending.

## Direct-horizon forecasting / Days 7-8 — 12 October 2026

Implemented and independently validated trained forecasting on approved processed files only; no raw CSV analysis, synthetic training rows or changed scope. Of 229 categories, 201 meet >=90% positive-week coverage in complete weeks 19-71. Eligibility uses the first validation training cutoff rather than full-window future outcomes. Partial week 102 is excluded from all forecast history. Revenue is SALES_VALUE (USD); quantities remain physically unverified.

Chronology: validation blocks 72-77, 78-83 and 84-89, expanding training cutoffs 71/77/83. The final held-out target block is 90-101; evaluation models fit labels <=89 and remain frozen. Rolling-origin evaluation can observe earlier test revenue when a later origin is reached, without refitting models. Origins start at 89 for every horizon, so h1/2/3/4 have 12/11/10/9 evaluable origins. There are 8,442 matched category/origin/horizon test pairs and 1,809 four-week totals across nine common origins. This avoids training on outcomes unavailable at earlier forecast origins. Methods within each horizon share exactly the same rows and baselines. Overlapping totals are dependent observations, not confidence-interval samples.

Four direct global HistGradientBoostingRegressor models use explicit commodity categorical codes and origin-scale-normalized targets. Scikit-learn's [official estimator reference](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.HistGradientBoostingRegressor.html) was checked for native categorical/missing-value support. Saved environment is 1.9.1; version/source/settings/artifact fingerprints are checked before loading local pickles. Features and exact cohort mapping are saved. Unknown categories are rejected.

Features: revenue lags 1-4, origin-only rolling means/population std over 4 and 8 weeks, log origin scale, observed loyalty-discount line share, guarded display/mailer shares and coverage/missingness, and target synthetic calendar cyclic positions. Here lag1 is the just-completed origin week; for each horizon all observed summaries end at that origin. Scale is max(origin eight-week mean, $1), not a full-series mean. Categories with no lines have unknown discount share, not fabricated zero. Promotion flags use only observed past matched sales keys, at least .50 coverage/five matched keys; unknowns are retained. No planned future promo data, holiday flags, actual holiday interpretations or lag52 model feature are used. Seasonal naive alone uses target week minus 52.

Three fixed model candidates differ in max_leaf_nodes 7/15/31; all use 150 iterations, learning rate .05, min_samples_leaf 20, L2 1 and seed 42. Random early-stopping holdouts are disabled. Candidate choice minimizes pooled validation WAPE across the three folds per horizon. The global serving method per horizon then minimizes validation WAPE among the chosen trained model and three baselines. Baselines are origin revenue, origin four-week mean held fixed for each horizon, and target-minus-52 revenue. This moving-average definition is direct/fixed-origin and differs from the separately labelled legacy recursive subperiod baseline.

Current serving selection is gradient boosting for h1-2 and seasonal naive for h3-4. This is selected on validation, not on final test errors. Production models are separately refit on known labels through complete week 101; saved evaluation models reproduce the frozen test protocol. Negative model predictions are floored at zero and their count is saved. No source observations/outliers are clipped or removed.

| Horizon | Gradient boosting WAPE | Naive | Seasonal naive | Moving average | Served method |
| --- | --- | --- | --- | --- | --- |
| 1 | 16.05% | 21.35% | 16.49% | 18.03% | Gradient boosting |
| 2 | 16.30% | 22.16% | 16.64% | 18.27% | Gradient boosting |
| 3 | 17.29% | 24.26% | 16.76% | 18.94% | Seasonal naive (52 weeks) |
| 4 | 16.80% | 22.11% | 16.03% | 18.51% | Seasonal naive (52 weeks) |

Model relative WAPE improvement versus naive: +24.84/+26.47/+28.75/+24.00%. Versus seasonal naive: +2.70/+2.10/-3.12/-4.85%. These are relative error reductions, not percentage points or accuracy percentages. Seasonal naive has lower overall RMSE at all four horizons. The trained model beats all three baselines for 87/81/82/71 of 201 categories; no uniform superiority claim is allowed.

| Method | Four-week-total WAPE |
| --- | --- |
| Gradient boosting | 10.44% |
| Naive | 17.83% |
| Seasonal naive (52 weeks) | 10.16% |
| Four-week moving average (fixed origin) | 12.34% |
| Validation-selected forecast | 9.07% |

Four-week selected WAPE 9.07% is better than seasonal naive 10.16%, moving average 12.34% and naive 17.83% on the common nine-origin held-out totals. Trained-only 10.44% loses to seasonal naive. Reporting totals does not establish future accuracy or profitability.

Week 92 is retained. Per-target-week mixed-horizon errors and pretest-volatility bands (CV <= .75 versus > .75) are saved. They describe model failures and do not diagnose an underlying department/store cause or holiday effect. forecasts improve/losses per category and baseline are in forecast_improvement.csv with undefined zero-denominator comparisons retained as missing.

Independent validation reconstructs every model feature from origin-truncated processed histories, reconciles source/covariate keys, refits every tuning candidate and both frozen and production models, verifies validation-only choices, reproduces all backtest/future predictions and recomputes category/horizon/overall/four-week/improvement/week/volatility metrics. Before final execution, undefined loyalty shares were corrected to remain missing; no candidate/serving-rule changes were made to optimize held-out performance. The final report is PASS.

Saved artifacts: forecast_model.pkl, forecast_evaluation_models.pkl; forecast_panel, forecast_covariates, forecast_backtest, forecast_validation_predictions, forecast_next_weeks, forecast_total_backtest; tuning/metric/improvement/error CSVs and standalone diagnostics HTML. predict_next_weeks(exact_commodity,h=1..4) loads validated local models and returns direct predictions. Full approved-window actual queries serve these saved results; explicit subperiods use labelled exploratory baselines. The Judge recomputes horizon and four-week metrics, target alignment, totals and validation-selected methods. App source/model signatures invalidate stale answers; changed forecasting settings are rejected.

Final verification: 45 unit tests and six actual tool/Judge/UI flows passed, including model-setting invalidation and unsupported/subperiod/scope behavior. README, CLAUDE and local_readiness are updated. Forecast technical stage is complete for local demonstration. Recommendations, human business usefulness/temporal robustness review, Python 3.11, ADK/GCP and final Review 3/public launch remain open. Next technical step: two independent recommendation rankings with documented weights and evidence.

## Two recommendation rankings / Day 9 — 13 October 2026

Implemented separate forecast/category and segment/affinity hypotheses from independently validated processed snapshots. No raw files, scope edits, fabricated metrics or synthetic project results. Source/config/library/upstream/build/validation/artifact fingerprints are required before use.

Cohort is the saved top-100 category-score table. All 100 currently have saved four-step forecasts and sufficient group evidence. Both lists retain 100 rows; their top tens share only DIAPERS & DISPOSABLES. They remain separate evidence lists, without a merged score or chosen winner. Scores are comparable within each method only. Automatic business arbitration is not implemented.

A weights: .60 percentile-ranked forecast growth + .40 product_score/100. Growth = selected forecast revenue for weeks 102-105 / observed complete-week revenue 98-101 - 1. A uses the existing validation-selected forecast methods unchanged. Category-specific historical four-week forecast WAPE and the best matched baseline WAPE are shown as separate quality evidence, not recommendation accuracy or campaign-effect estimates.

B weights: .60 percentile-ranked pooled target-group affinity + .40 percentile-ranked group momentum (revenue 98-101 / revenue 94-97 - 1). Group selection requires saved revenue/week median index >=1.25; current group 1 has 1,355 households and 84.4585% of approved revenue. This rule is observed spending, not profit or lifetime value. Pooled affinity = category share of selected groups' revenue / category share of all revenue. Distinct buyer counts may be added across disjoint segment assignments; the validator computes unique household counts directly. At least 50 target buyers are required.

Eligible raw components use average tied percentile ranks mapped to [0,1]; constant eligible values receive .5. Zero/negative denominators and unavailable evidence remain missing. Ineligible entries are retained with explicit reasons, null score/rank and review label, rather than silently removed or imputed as zero. Scores multiply weighted components by 100; ties sort alphabetically. No ranking weight was fit or optimized on promotion outcomes.

Provisional labels: promote requires rank <=10 and growth/momentum >=.05; B also requires affinity >=1.05. Decline below -.05 causes review. A total WAPE above 25% or undefined causes review. Remaining eligible rows are maintain. All execution statuses are review_required, including promote. Current counts: A 7 promote / 40 maintain / 53 review; B 0 promote / 80 maintain / 20 review. B's top ten is entirely maintain. We did not change thresholds to manufacture a desired number of promotions.

All 100 promotion associations remain unavailable; None/NaN never becomes zero effect. Forecast revenue describes an organic outlook, not incremental promoted revenue. Margins, discount cost, campaign spend, capacity, causal response and ROI are not modeled. Both top-ten business plausibility reviews by Megh remain pending; no acceptance or authorization to run campaigns is inferred from a next request.

The group covers most overall revenue, and its category affinity spans only .9345-1.0798 in the scoring cohort. Rank normalization can amplify small absolute differences. Raw affinity, group support and conflicting momentum/forecast evidence remain visible. A's lead ICE CREAM/MILK/SHERBTS has forecast growth +8.63% while group momentum is -5.95%. B's lead SEAFOOD-FRESH has group momentum +31.53% while forecast growth is -11.85%. Neither list is automatically preferred.

Snapshot/as-of end is week 102/day 711. Category scores and saved segment assignments/affinity include the partial terminal week 102. Temporal comparisons use completed weeks through 101, and forecast weeks 102-105 overlap partial source week 102. This is explicitly a current-snapshot ranking, not a point-in-time recommendation backtest or four fully future weeks. No recommendation accuracy/precision is claimed.

New artifacts: recommendations.parquet, recommendation_category_evidence.parquet, recommendation_segment_weekly.parquet; recommendation_build_report.json, recommendation_validation.json, recommendation_top10.csv and standalone recommendation_diagnostics.html. Findings are in recommendation_findings.md. Independent validation recomputes all source totals, direct pool affinity/buyers, recent/prior momentum, forecast-versus-baseline quality, eligibility, normalization, scores, order, labels and overlap. Its initial index/column sorting ambiguity was fixed; final status PASS.

Supervisor now supports Which products should we promote next month? (commodity categories), routed to the Forecast & Recommendation specialist. The deterministic Judge validates both evidence lists, counts, components, growth, labels, shared membership and absence of unsupported winners/profit claims. Full approved weeks 19-102 are required; subperiod requests and changed settings are rejected. Model/source/report signatures invalidate previous dashboard answers.

53 unit tests, seven actual tool/Judge flows and seven Streamlit result/chart/transparency flows pass. Both ranking formulas remain technically complete for local demonstration; human plausibility, actual recommendation effectiveness, business arbitration and final public launch remain open. Next technical step: week-92 source diagnosis and consolidated ML evaluation, followed by cloud-access setup. Python 3.11, ADK/Gemini/GCP and final Review 3 remain pending.


## Week-92 diagnosis, ML freeze and cloud preparation — 13 October 2026

Added processed-only week-92 department/store/commodity diagnostics against mean complete weeks 90/91/93/94. This retrospective comparator includes later observed weeks and is not a forecast feature or causal counterfactual. Approved scope, raw/master/aggregates, trained models and recommendations are unchanged.

Revenue $94,551.58 vs $76,558.105 (+23.5030%); baskets 2,962 vs 2,509 (+18.0550%); households 1,379 vs 1,286.75 (+7.1692%); lines 30,826 vs 26,450.5 (+16.5422%); basket value $31.9215 vs $30.5134 (+4.6148%). Reference ABV uses pooled revenue/baskets. Basket-count and basket-value factors reconcile with revenue; neither isolates physical volume, price or mix.

Configured breadth rules: store reference mean >=$25; major department reference share >=1%; at least three increasing major departments, >=50% eligible stores increasing, increasing departments covering >=50% major-department reference revenue, top store <=25% positive store changes. Actual 75/115 stores and 8/9 major departments increase, reference share 93.8818%, top store 3.3341% of positive changes. Grocery change $10,251.1125, 56.3972% positive department changes. Group distinct baskets/households are not added.

Decision: retain all week records without adjustment. Observed breadth does not establish an isolated-store artefact; it also does not prove genuine demand or exclude a system-wide issue. Cause unknown; no holiday, promotion effect or corruption inferred. Independent validator reproduces every group contribution, share, weekly distinct count, flag, aggregate benchmark and breadth criterion. Full-window evidence requires current source/settings/artifact fingerprints; the Judge rejects fabricated causes.

Consolidated evaluation_ml.md/json preserves actual segmentation/category stability/forecast baseline comparisons/separate recommendation metrics. All 28 processed Parquet names/types/row counts/SHA256s frozen in processed_schema_manifest.json and independently checked. Intentional schema changes require regeneration/validation. eda_findings.md records supported findings without inventing missing original-guide EDA.

Installed Google CLI 588.0.0 from official archive after SHA256 verification, with six contained archive links copied for Windows. Optional google-genai==2.30.0 installed; pip check passes. Current SDK cloud backend uses enterprise=True with explicit ADC/project; configurable gemini-3.5-flash/global/v1 checked against official SDK/quickstart/lifecycle docs. Future app region us-central1 remains separate. Installation is not cloud proof.

Preflight lacks project ID and ADC. No real model response fabricated: stub tests are not access proof. --execute uses one fixed greeting, can incur normal model charges, and requires an actual nonempty response for PASS in vertex_smoke_test.json. No data upload, project creation, billing/API/IAM/resource change or public deployment executed. docs/cloud_setup.md has reviewable account instructions; user completes account sign-in. Existing agents/Judge remain deterministic.

62 unit tests, eight actual tool/Judge flows and eight Streamlit flows pass; both Day-10 validators PASS. Local demo ready, public launch false. Next: cloud access proof after project/sign-in, then ADK. Human usefulness/temporal robustness, Python 3.11, household/decomposition tools, deployment, final evaluation and Review 3 remain open.


## Conversational responses and practical suggestions — 13 October 2026

The user requested a dashboard that responds like GPT and gives suggestions. Implemented chat input/message history, natural whole-question aliases, remembered follow-ups and evidence-derived next steps. This is an interface/orchestration change; accepted scope, retained raw/master/aggregate rows, trained models, score/recommendation definitions and the 28-table schema manifest are unchanged.

Questions resolve to registered Supervisor routes; tools rerun on the current validated snapshot and their results pass the existing Judge. Separate checked paragraphs derive specific products/groups/categories and provisional actions from that evidence. Suggestions are reviewed hypotheses: promote stays provisional, maintain/review are preserved, no campaign authorization, profit, causal response, ROI or guaranteed performance is claimed. Physical units remain unverified. Explicit limitations are displayed, and risk follow-ups put them first.

Conversation retains the last successful analysis through clarification messages and preserves forecast commodity. Why/next-step/risk requests refresh the evidence. History is browser-session only, capped at 24 complete turns, reset by New conversation and data/policy/week-scope changes. A rerun does not duplicate a submission. Unknown or out-of-domain requests clarify; extra filters/multiple tasks are not silently discarded. Existing eight exact examples remain available.

Optional Gemini adapter uses the checked google-genai JSON-schema interface: supported intent/category classification, followed by paragraph-ID selection. It requires a real model-access PASS matching current cloud settings plus local ADC/project prerequisites and is off by default. Only the submitted question, prior route and checked aggregate paragraphs are sent; raw transaction rows and household histories are not sent. The model cannot introduce new numeric claims or unrestricted prose. Invalid model IDs/blocks, missing limitations or call failures yield a clearly labelled local response. Authentication errors are not exposed. SDK stub tests are separate from actual cloud proof. No real Gemini chat was executed; project/sign-in remain missing, and this is not an OpenAI GPT integration or ADK implementation.

Validation: 77 unit tests; eight actual processed-data tool/Judge and dashboard examples; seven natural chat flows; additional unknown-request, topic continuation, starter/follow-up, new conversation, cap, no-duplicate rerun and source/scope invalidation checks. outputs/chat_validation.json records local actual-data PASS with actual_cloud_chat_verified=false. Next actual cloud proof/sign-in, human usefulness, Python 3.11, remaining tools, ADK/deployment and Review 3/public launch remain pending.


## Brief answers, detailed explanations and action controls — 13 October 2026

The user asked for short and long chat answers, what to do next, and useful additional features. Added a concise primary answer, explicit proposed next steps, expandable detailed explanation, Short + details / Detailed preference, remembered short/detail requests and native copy/Markdown download controls. Charts default collapsed to keep conversation readable.

All formats derive from the same validated specialist result. Short summaries keep essential revenue/cause/provisional-action qualifications. Detailed answers preserve explanation, all proposed actions, caveats, scope and revenue definition; forecasts include matched baseline WAPE comparisons rather than hiding losing methods. Downloads include both answer lengths and their evidence context. Every presentation field is regenerated and compared before display; fabricated edits are rejected.

Preference changes do not duplicate chat submissions or rerun analytics. Explicit short/detail requests refresh the prior successful analysis/category. Presentation version 2 clears outdated stored reply shapes. No scope, raw/master/aggregate, score/ranking, saved model or processed-schema change. No campaign authorization or cloud request occurred.

81 unit tests; eight actual-data tool/Judge and dashboard flows; nine natural chat flows passed. Checks include consistent short/detail figures, preserved baseline failures, provisional action qualifications, copy/download content, length preference, follow-ups, rerun/reset/cap and source/scope invalidation. Local demo ready; cloud project/ADC/live proof, human usefulness, Python 3.11, remaining tools, ADK/deployment and Review 3/public launch remain pending.

## Local-only VS Code scope — 13 October 2026

The user explicitly rejected deployment and GCP and requested all app work in VS Code. This supersedes the handoff's cloud/ADK deployment plan and earlier cloud-access next steps. Cloud project IDs, ADC, billing, APIs, hosting and public launch are no longer requirements or blockers for this app. The academic analytics review remains separate.

Added .vscode launch/tasks/settings/extensions files and scripts/run_local.py. F5 selects the existing project venv, checks local dependencies/current master scope, starts headless Streamlit on 127.0.0.1:8501 in the integrated terminal and uses the installed openIntegratedBrowser server-ready action. The integrated-browser capability and debug extension were found installed. Browser profiles/settings stay inside VS Code; app code never opens an external browser. .streamlit/config.toml disables usage reporting and binds loopback. No extra extension, model download or cloud dependency was installed.

Removed the cloud adapter import, connection lookup, Gemini toggle/client construction and cloud setup prompts from app.py. LOCAL_ONLY_MODE=True blocks retired provider helpers before credentials/client creation and disables cloud-check/installer script actions. Even an injected model is ignored by the active chat path. Historical provider-contract tests explicitly use stubs with a test-only override; they do not invoke a real SDK/provider. Existing cloud artifacts/install files are retained for provenance and are not used by the app.

Short/detailed answers, next steps, remembered follow-ups, copy/download, charts and all validated analytics remain. Source data, approved business scope, models, ranking formulas and the 28 processed schemas are unchanged. Chat presentation version 3 clears stale stored reply shapes.

Verification: 84 unit tests; eight actual processed-data tool/Judge/dashboard flows and nine natural chat flows PASS. Exact local launcher started successfully; its local health endpoint returned HTTP 200. Local prerequisites, server-ready URL pattern and installed editor-browser action were checked. Actual automated F5/editor UI interaction was not performed. Cloud-check and installer entrypoints returned disabled without authentication/network/resource changes.

README and CLAUDE were rewritten for the active local workflow; earlier versions/readiness/cloud preflight are archived under docs/history. cloud_setup.md is marked retired. local_readiness.json now tracks requested local readiness and excludes cloud/deployment gates. Follow docs/local_setup.md and press F5 in VS Code. Stop another app server on port 8501 first; unrelated processes are never killed.

Current Python 3.14.4 remains provisionally tested; the original 3.11 target is unfulfilled. Human usefulness/temporal robustness, household/decomposition tools, final academic evaluation and Review 3 mapping remain research work. No GCP, external-model integration or deployment will be pursued without a new explicit instruction.
## Review III exact values and labelled assumptions — 13 October 2026

The user supplied FMCG_Product_Intelligence_System_-_MTech_Review_III-1.pptx and requested accurate blank values, necessary project changes, and assumptions for missing features. The 19-slide document describes several unimplemented/out-of-scope cloud methods. Its content did not override the active no-GCP/no-deployment instruction. Revised 17 content slides, retaining the cover, closing slide and all package resources.

Resolved all 36 original blank slots with measured values or explicit not-implemented/assumption status. Approved analysis: 2,216,262 lines; retained master 2,581,333; revenue USD 6,237,807.19; baskets 218,960; households 2,492; ABV 28.4883412; mean baskets/household 87.8651685. Top GROCERY/DRUG GM/PRODUCE share 76.7775706%. Discounted-sales share 49.7630711% uses recorded revenue on any negative retail/coupon/coupon-match discount line, not causal exposure/lift.

Complete weeks 19-101 peak at week 92, USD 94,551.58. Mean weekly revenue in 60-101 versus 19-59 changes +5.3302015%. No holiday cause, statistically proven growth or physical demand is inferred.

K-Means stays at validated k=2. To fill four group rows without forcing or inventing clusters, the revised slide explicitly uses the already-saved four-rule RFM baseline: Frequent recent higher-spend 512 / 45.1404% revenue / USD 5,499.5509 mean window spend; Recently active 980 / 33.4203% / USD 2,127.2375; Long-gap lower-spend 814 / 10.4326% / USD 799.4668; Long-gap higher-spend 186 / 11.0067% / USD 3,691.2818. Those names and rates are descriptive, not validated Champions/Loyal/At-Risk semantics. The highest-revenue rule group accounts for 20.5457% households and 45.1404% revenue. Separate actual K-Means profiles remain available.

Forecast blanks were relabelled to the implemented commodity-level direct gradient-boosting method. H1 matched held-out MAPE 29.4671% vs naive 33.9955%, RMSE USD 115.4521 vs 161.2966. History starts 19; earliest usable training labels 27/28/29/30 after eight-week feature warm-up; frozen label cutoff89, target test90-101. Four-week selected WAPE9.0693 versus trained-only10.4412 and seasonal naive10.1616 is a separate comparison. No ARIMA result, eight-week forecast or 90% interval is invented.

Top category scores: BAG SNACKS, BAKED BREAD/BUNS/ROLLS, FLUID MILK PRODUCTS. The coupon/cross-sell example is explicitly illustrative future work without effect/ROI/campaign approval. GCP/Cloud Run/BigQuery/Gemini/ADK and public URL claims were replaced with the actual local Python/Parquet/scikit-learn/Streamlit/VS Code workflow. A local loopback URL is not a public deployment.

Project changes are reproducible reporting modules/build/validation scripts, scoped reporting constants, three integrity/metric tests and VS Code build/validate tasks. No raw data, processed/model artifacts, scope, learned models or scientific scoring parameters changed; no new processed table was added, so the 28-table schema freeze remains valid. 87 unit tests pass. Numeric/PPT package validation passed on the first draft; the final draft is regenerated after readiness/test-count documentation updates and validated again.

Original PPT preserved; filled copy and source-backed values/corrections are in outputs/review3. Numeric results are independently checked, original resources remain byte-identical, and all placeholder slots are resolved. Body text uses 18pt and normal autofit. A local font-metric estimate found body text fits; native PowerPoint rendering and human usefulness/academic review remain unverified. No assumption is used as a fabricated benchmark or production-completion claim.