"""Shared settings. Approved core-consumables scope and week-19 window."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRANSACTION_FILE = PROJECT_ROOT / "transaction_data.csv"
PRODUCT_FILE = PROJECT_ROOT / "product.csv"
REVENUE_COLUMN = "SALES_VALUE"
CURRENCY = "USD"
DIAG_TARGET_WEEK = 92
RANDOM_STATE = 42
REQUIRED_COLUMNS = ["household_key", "BASKET_ID", "WEEK_NO", "DAY", "PRODUCT_ID", "QUANTITY", REVENUE_COLUMN]
PRODUCT_COLUMNS = ["PRODUCT_ID", "COMMODITY_DESC", "SUB_COMMODITY_DESC"]
TOP_PRODUCTS = 10
FORECAST_HORIZON = 4
FORECAST_HOLDOUT = 12
FORECAST_MIN_WEEKS = 28
MOVING_AVERAGE_WEEKS = 4
SEASONAL_PERIOD = 52
CLUSTER_K_VALUES = range(2, 11)
MIN_CLUSTER_SHARE = 0.05
SILHOUETTE_SAMPLE_SIZE = 1000
KMEANS_N_INIT = 10
DAYS_PER_WEEK = 7
# An explicit business interpretation for the demo question, shown to the user.
CATEGORY_ALIASES = {"milk": "FLUID MILK PRODUCTS"}
DEMO_QUESTIONS = [
    "What are the sales KPIs?",
    "Show weekly sales trend",
    "Show top products",
    "Show customer segments",
    "Show category intelligence",
    f"Investigate sales in week {DIAG_TARGET_WEEK}",
    "Which products should we promote next month?",
    "Forecast milk demand for next month",
]

# Reproducible data preparation from the supplied master guide.
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"
MASTER_FILE = PROCESSED_DIR / "transactions_master.parquet"
MASTER_REPORT_FILE = OUTPUTS_DIR / "master_build_report.json"
PRODUCT_LOOKUP_FILE = PROCESSED_DIR / "product_lookup.parquet"
DEMOGRAPHIC_FILE = PROJECT_ROOT / "hh_demographic.csv"
SOURCE_CSV_FILES = (
    "transaction_data.csv", "product.csv", "hh_demographic.csv",
    "campaign_desc.csv", "campaign_table.csv", "coupon.csv",
    "coupon_redempt.csv", "causal_data.csv",
)
CSV_CHUNK_ROWS = 250000
HASH_CHUNK_BYTES = 8 * 1024 * 1024
REVENUE_TOLERANCE_USD = 0.01
PARQUET_COMPRESSION = "snappy"
CALENDAR_DAY_ONE = "2015-12-30"  # Synthetic calendar anchor; not verified purchase dates.
ANALYSIS_START_WEEK = 19
ANALYSIS_END_WEEK = None  # Through the last observed week; forecasting uses full weeks only.
FORECASTABLE_WEEK_SHARE = 0.90

# None means UNKNOWN, not an empty exclusion list. Exact names are absent from the guide.
# Fill these only from the earlier scope definition or an explicit user decision.
EXCLUDED_DEPARTMENTS = ['',
 'AUTOMOTIVE',
 'CHARITABLE CONT',
 'CHEF SHOPPE',
 'CNTRL/STORE SUP',
 'COUP/STR & MFG',
 'DELI/SNACK BAR',
 'ELECT &PLUMBING',
 'FLORAL',
 'GARDEN CENTER',
 'GM MERCH EXP',
 'HOUSEWARES',
 'KIOSK-GAS',
 'MEAT-WHSE',
 'MISC SALES TRAN',
 'MISC. TRANS.',
 'PHARMACY SUPPLY',
 'PHOTO',
 'POSTAL CENTER',
 'PROD-WHS SALES',
 'RESTAURANT',
 'RX',
 'TOYS',
 'TRAVEL & LEISUR',
 'VIDEO',
 'VIDEO RENTAL']
EXCLUDED_COMMODITIES = ['',
 '(CORP USE ONLY)',
 'BOTTLE DEPOSITS',
 'COSMETIC ACCESSORIES',
 'COUPON',
 'COUPON/MISC ITEMS',
 'COUPONS/STORE & MFG',
 'DELI SUPPLIES',
 'FUEL',
 'MEAT SUPPLIES',
 'MISCELLANEOUS',
 'MISCELLANEOUS(CORP USE ONLY)',
 'NO COMMODITY DESCRIPTION',
 'PHARMACY',
 'PROD SUPPLIES',
 'UNKNOWN']
DRUG_GM_REVIEW_COMMODITIES = ['APPAREL',
 'AUDIO/VIDEO PRODUCTS',
 'AUTOMOTIVE PRODUCTS',
 'BATTERIES',
 'BOOKSTORE',
 'CANDLES/ACCESSORIES',
 'CHARCOAL AND LIGHTER FLUID',
 'CHRISTMAS  SEASONAL',
 'CIGARETTES',
 'CIGARS',
 'CONTINUITIES',
 'COOKWARE & BAKEWARE',
 'COUPON/MISC ITEMS',
 'DOLLAR VALUE PRODUCTS',
 'DOMESTIC GOODS',
 'EASTER',
 'ELECTRICAL SUPPPLIES',
 'FALL AND WINTER SEASONAL',
 'FILM AND CAMERA PRODUCTS',
 'FIREWORKS',
 'GLASSES/VISION AIDS',
 'GLASSWARE & DINNERWARE',
 'GREETING CARDS/WRAP/PARTY SPLY',
 'HAIR CARE ACCESSORIES',
 'HALLOWEEN',
 'HARDWARE SUPPLIES',
 'HOME FREEZING & CANNING SUPPLY',
 'HOME FURNISHINGS',
 'HOSIERY/SOCKS',
 'IN-STORE PHOTOFINISHING',
 'J-HOOKS',
 'KITCHEN GADGETS',
 'LAWN AND GARDEN SHOP',
 'LONG DISTANCE CALLING CARDS',
 'MAGAZINE',
 'NEWSPAPER',
 'OVERNIGHT PHOTOFINISHING',
 'PERSONAL CARE APPLIANCES',
 'PLASTIC HOUSEWARES',
 'PORTABLE ELECTRIC APPLIANCES',
 'PREPAID WIRELESS&ACCESSORIES',
 'PROPANE',
 'SEWING',
 'SPORTS MEMORABLILIA',
 'SPRING/SUMMER SEASONAL',
 'TICKETS',
 'TOBACCO OTHER',
 'TOYS AND GAMES',
 'VALENTINE',
 'WATCHES/CALCULATORS/LOBBY']
DRUG_GM_POLICY = 'exclude'
WEIGHTED_COMMODITIES = None  # No verified weighted-product rule was supplied.


def in_analysis_window(data):
    """Return the configured week mask; no calendar-date interpretation is implied."""
    mask = data["WEEK_NO"] >= ANALYSIS_START_WEEK
    if ANALYSIS_END_WEEK is not None:
        mask &= data["WEEK_NO"] <= ANALYSIS_END_WEEK
    return mask
RAW_TRANSACTION_COLUMNS = ["household_key", "BASKET_ID", "DAY", "PRODUCT_ID", "QUANTITY", "SALES_VALUE", "STORE_ID", "RETAIL_DISC", "TRANS_TIME", "WEEK_NO", "COUPON_DISC", "COUPON_MATCH_DISC"]
LOOKUP_COLUMNS = ["PRODUCT_ID", "MANUFACTURER", "DEPARTMENT", "BRAND", "COMMODITY_DESC", "SUB_COMMODITY_DESC", "CURR_SIZE_OF_PRODUCT"]


# Reference counts from the guide are advisory; exact historical names remain unavailable.
DOCUMENTED_SCOPE_COUNTS = {"Departments": 21, "Commodities": 16, "DRUG GM review commodities": 32}

# New proposed boundary; these are NOT the missing historical scope lists.
PROPOSED_SCOPE_ID = "core_consumables_v1"
PROPOSED_SCOPE_DIR = OUTPUTS_DIR / "proposed_scope"
PROPOSED_SCOPE_REFERENCE = "https://nielseniq.com/global/en/insights/analysis/2022/what-is-the-difference-between-fmcg-and-cpg/"
PROPOSED_SCOPE_DEPARTMENT_EXCLUSIONS = {
    "Unclassified label; no reliable retail-product assignment": ["", "CHEF SHOPPE"],
    "Donation, coupon accounting, store expense or unidentified transaction": ["CHARITABLE CONT", "CNTRL/STORE SUP", "COUP/STR & MFG", "GM MERCH EXP", "MEAT-WHSE", "MISC SALES TRAN", "MISC. TRANS."],
    "Store supplies rather than household consumption": ["DELI/SNACK BAR", "PHARMACY SUPPLY", "PROD-WHS SALES"],
    "Durables or specialist merchandise outside the core-consumables boundary": ["AUTOMOTIVE", "ELECT &PLUMBING", "FLORAL", "GARDEN CENTER", "HOUSEWARES", "TOYS", "TRAVEL & LEISUR", "VIDEO"],
    "Fuel or services outside the proposed retail-consumables boundary": ["KIOSK-GAS", "PHOTO", "POSTAL CENTER", "RESTAURANT", "VIDEO RENTAL"],
    "Prescription pharmacy outside the proposed grocery/OTC boundary": ["RX"],
}
PROPOSED_SCOPE_COMMODITY_EXCLUSIONS = {
    "Unclassified or internal label; conservatively excluded pending a SKU review": ["", "(CORP USE ONLY)", "MISCELLANEOUS", "MISCELLANEOUS(CORP USE ONLY)", "NO COMMODITY DESCRIPTION", "UNKNOWN"],
    "Deposit or coupon bookkeeping rather than merchandise": ["BOTTLE DEPOSITS", "COUPON", "COUPON/MISC ITEMS", "COUPONS/STORE & MFG"],
    "Store operational supplies rather than customer consumables": ["DELI SUPPLIES", "MEAT SUPPLIES", "PROD SUPPLIES"],
    "Fuel or pharmacy outside this proposed boundary": ["FUEL", "PHARMACY"],
    "Mixed jewellery/applicator accessory category; may omit consumables until SKU review": ["COSMETIC ACCESSORIES"],
}
PROPOSED_SCOPE_DRUG_GM_EXCLUSIONS = {
    "Durable apparel, equipment or household accessories": ["APPAREL", "AUDIO/VIDEO PRODUCTS", "COOKWARE & BAKEWARE", "ELECTRICAL SUPPPLIES", "GLASSES/VISION AIDS", "GLASSWARE & DINNERWARE", "HAIR CARE ACCESSORIES", "HARDWARE SUPPLIES", "HOME FREEZING & CANNING SUPPLY", "HOME FURNISHINGS", "HOSIERY/SOCKS", "KITCHEN GADGETS", "LAWN AND GARDEN SHOP", "PERSONAL CARE APPLIANCES", "PORTABLE ELECTRIC APPLIANCES", "SEWING", "SPORTS MEMORABLILIA", "TOYS AND GAMES", "WATCHES/CALCULATORS/LOBBY"],
    "Books, media, photography, telecommunications or tickets": ["BOOKSTORE", "FILM AND CAMERA PRODUCTS", "IN-STORE PHOTOFINISHING", "LONG DISTANCE CALLING CARDS", "MAGAZINE", "NEWSPAPER", "OVERNIGHT PHOTOFINISHING", "PREPAID WIRELESS&ACCESSORIES", "TICKETS"],
    "Broad seasonal/promotion label; conservative category exclusion may omit consumables": ["CHRISTMAS  SEASONAL", "CONTINUITIES", "EASTER", "FALL AND WINTER SEASONAL", "GREETING CARDS/WRAP/PARTY SPLY", "HALLOWEEN", "SPRING/SUMMER SEASONAL", "VALENTINE"],
    "Utility supplies outside the chosen food/personal/home-care boundary": ["AUTOMOTIVE PRODUCTS", "BATTERIES", "CHARCOAL AND LIGHTER FLUID", "FIREWORKS", "PROPANE"],
    "Mixed broad merchandise category; excluded until a product-level review": ["CANDLES/ACCESSORIES", "DOLLAR VALUE PRODUCTS", "DOMESTIC GOODS", "J-HOOKS", "PLASTIC HOUSEWARES"],
    "Tobacco is outside this proposed core-consumables study; not a claim that it cannot be FMCG": ["CIGARETTES", "CIGARS", "TOBACCO OTHER"],
    "Coupon bookkeeping rather than merchandise": ["COUPON/MISC ITEMS"],
}
PROPOSED_SCOPE_RETAINED_REVIEW_NOTES = {
    "BROOMS AND MOPS": "Retained as cleaning aids; includes durable tools as well as pads/sponges. SKU refinement is pending.",
    "DISPOSIBLE FOILWARE": "Retained as food-preparation disposables; some grill accessories may need SKU refinement.",
    "HOME HEALTH CARE": "Retained in broad OTC/home-health scope; includes durable health accessories, so SKU refinement is pending.",
    "INFANT CARE PRODUCTS": "Retained in baby-care scope; includes feeding accessories as well as consumables.",
    "NON EDIBLE PRODUCTS": "Subcommodity labels include sun care, baby care and laundry consumables; retained despite the generic label.",
    "SPIRITS": "Alcoholic beverages retained as retail beverage consumables; this is an explicit study choice.",
    "PET CARE SUPPLIES": "Retained in household/pet-care scope; may mix consumables with accessories.",
}

# Saved RFM/segmentation stage. Extra seeds are initialization stress tests only.
MODELS_DIR = PROJECT_ROOT / "models"
SEGMENT_FEATURES = ["recency_days", "baskets_per_week", "revenue_per_week"]
RFM_SCORE_BINS = 5
RFM_HIGH_SCORE = 4
RFM_LOW_RECENCY_SCORE = 2
RFM_ACTIVE_SCORE = 3
STABILITY_SEEDS = (42, 7, 21, 84)
MIN_STABILITY_MEAN_ARI = 0.80
SEGMENT_MIN_HOUSEHOLDS = 2
PROFILE_HIGH_RATIO = 1.25
PROFILE_LONG_GAP_DAYS = 28
SEGMENT_BUILD_FILE = OUTPUTS_DIR / "segmentation_build_report.json"
SEGMENT_VALIDATION_FILE = OUTPUTS_DIR / "segmentation_validation.json"
SEGMENT_PROFILES_FILE = PROCESSED_DIR / "segment_profiles.parquet"
HOUSEHOLD_SEGMENTS_FILE = PROCESSED_DIR / "household_segments.parquet"
SEGMENT_MODEL_SOURCE = "household_segments.parquet + segment_profiles.parquet + saved RFM models"
SEGMENT_TABLE_NAMES = ("household_rfm", "clustering_features", "household_clusters", "household_segments", "segment_profiles", "segment_product_affinity", "segment_demographic_profiles")
SEGMENT_OUTPUT_NAMES = ("clustering_evaluation.csv", "clustering_stability.csv", "rfm_cluster_comparison.csv", "clustering_seed_assignments.parquet", "clustering_diagnostics.html")
SEGMENT_MODEL_NAMES = ("scaler.pkl", "kmeans_model.pkl")


# Category intelligence: descriptive analyst index, not causal/learned business value.
CAUSAL_FILE = PROJECT_ROOT / "causal_data.csv"
DISPLAY_CODES = ("0", "1", "2", "3", "4", "5", "6", "7", "9", "A")
MAILER_CODES = ("0", "A", "C", "D", "F", "H", "J", "L", "P", "X", "Z")
PROMOTION_CODE_REFERENCE = "https://bradleyboehmke.r-universe.dev/completejourney/doc/manual.html#promotions_sample"
PROMO_PROGRESS_CHUNKS = 20
PROMO_MIN_GROUP_WEEKS = 8
PROMO_SHRINK_WEEKS = 12
PROMO_MIN_COVERAGE = 0.50
PROMO_MIN_MATCHED_KEYS = 5
PROMO_MAX_REVENUE_CV = 0.75
PROMOTION_TABLES = ("promotion_sales_keys", "promo_category_weekly")
PROMOTION_BUILD_FILE = OUTPUTS_DIR / "promotion_build_report.json"
PROMOTION_VALIDATION_FILE = OUTPUTS_DIR / "promotion_validation.json"
CATEGORY_TOP_N = 100
CATEGORY_DISPLAY_N = 20
CATEGORY_WEIGHTS = {"revenue_share": 0.25, "growth": 0.15,
                    "household_penetration": 0.20, "repeat_purchase_rate": 0.15,
                    "revenue_per_buyer": 0.15, "promotion_association": 0.10}
CATEGORY_SENSITIVITY_RUNS = 100
CATEGORY_WEIGHT_PERTURBATION = 0.20
CATEGORY_MIN_SPEARMAN = 0.90
CATEGORY_MIN_TOP20_OVERLAP = 0.80
CATEGORY_YOY_MIN_MONTH_PAIRS = 3
CATEGORY_NEUTRAL_COMPONENT = 0.50
CATEGORY_LABEL_TOP_N = 20
CATEGORY_SCORE_SCALE = 100
CATEGORY_TABLES = ("category_components", "product_scores", "promo_lift")
CATEGORY_OUTPUT_NAMES = ("category_weight_sensitivity.csv", "category_rank_ranges.csv", "category_diagnostics.html")
CATEGORY_BUILD_FILE = OUTPUTS_DIR / "category_build_report.json"
CATEGORY_VALIDATION_FILE = OUTPUTS_DIR / "category_validation.json"
CATEGORY_MODEL_SOURCE = "product_scores.parquet + promo_category_weekly.parquet"


# Direct-horizon global forecasting. Choices fixed before the final test block.
FORECAST_LAGS = (1, 2, 3, 4)
FORECAST_ROLLING_WINDOWS = (4, 8)
FORECAST_VALIDATION_FOLDS = 3
FORECAST_VALIDATION_WEEKS = 6
FORECAST_SCALE_FLOOR = 1.0
FORECAST_CALENDAR_MONTHS = 12
FORECAST_VOLATILITY_THRESHOLD = 0.75
FORECAST_PROMO_MIN_COVERAGE = 0.50
FORECAST_PROMO_MIN_KEYS = 5
FORECAST_PARAMS = [
    {"max_leaf_nodes": 7, "max_iter": 150, "learning_rate": 0.05, "min_samples_leaf": 20, "l2_regularization": 1.0},
    {"max_leaf_nodes": 15, "max_iter": 150, "learning_rate": 0.05, "min_samples_leaf": 20, "l2_regularization": 1.0},
    {"max_leaf_nodes": 31, "max_iter": 150, "learning_rate": 0.05, "min_samples_leaf": 20, "l2_regularization": 1.0},
]
FORECAST_FEATURES = ["commodity_code", "revenue_lag1", "revenue_lag2", "revenue_lag3", "revenue_lag4",
    "rolling_mean4", "rolling_std4", "rolling_mean8", "rolling_std8", "log_scale",
    "loyalty_lag1", "display_lag1", "mailer_lag1", "promo_coverage", "promo_unknown",
    "week_sin", "week_cos", "month_sin", "month_cos"]
FORECAST_METHODS = {"Gradient boosting": "gradient_boosting", "Naive": "naive",
    "Seasonal naive (52 weeks)": "seasonal_naive", "Four-week moving average (fixed origin)": "moving_average"}
FORECAST_TABLES = ("forecast_panel", "forecast_covariates", "forecast_backtest",
    "forecast_validation_predictions", "forecast_next_weeks", "forecast_total_backtest")
FORECAST_MODEL_NAMES = ("forecast_model.pkl", "forecast_evaluation_models.pkl")
FORECAST_OUTPUT_NAMES = ("forecast_tuning.csv", "forecast_metrics_by_category.csv",
    "forecast_metrics_overall.csv", "forecast_total_metrics.csv", "forecast_error_by_week.csv",
    "forecast_diagnostics.html", "forecast_improvement.csv", "forecast_error_by_volatility.csv")
FORECAST_BUILD_FILE = OUTPUTS_DIR / "forecast_build_report.json"
FORECAST_VALIDATION_FILE = OUTPUTS_DIR / "forecast_validation.json"
FORECAST_MODEL_SOURCE = "commodity_weekly.parquet + forecast_model.pkl + forecast_backtest.parquet"


# Day 9 recommendation hypotheses: defaults are analyst choices, not learned lift/ROI.
REC_METHODS = ("forecast", "segment")
REC_RECENT_WEEKS = 4
REC_DISPLAY_N = 10
REC_HIGH_SPEND_INDEX = 1.25
REC_MIN_TARGET_BUYERS = 50
REC_FORECAST_WEIGHTS = {"forecast_growth":0.60,"product_score":0.40}
REC_SEGMENT_WEIGHTS = {"target_affinity":0.60,"target_momentum":0.40}
REC_PROMOTE_GROWTH = 0.05
REC_REVIEW_DECLINE = 0.05
REC_PROMOTE_AFFINITY = 1.05
REC_MAX_FORECAST_WAPE = 25.0
REC_NEUTRAL_RANK = 0.50
REC_SCORE_SCALE = 100
REC_TABLES = ("recommendations","recommendation_category_evidence","recommendation_segment_weekly")
REC_OUTPUT_NAMES = ("recommendation_top10.csv","recommendation_diagnostics.html")
REC_BUILD_FILE = OUTPUTS_DIR / "recommendation_build_report.json"
REC_VALIDATION_FILE = OUTPUTS_DIR / "recommendation_validation.json"
REC_MODEL_SOURCE = "recommendations.parquet + validated forecast/category/segment evidence"
REC_UPSTREAM_BUILDS = {"category":CATEGORY_BUILD_FILE,"forecast":FORECAST_BUILD_FILE,"segment":SEGMENT_BUILD_FILE}
REC_UPSTREAM_VALIDATIONS = {"category":CATEGORY_VALIDATION_FILE,"forecast":FORECAST_VALIDATION_FILE,"segment":SEGMENT_VALIDATION_FILE}


# Week investigation: descriptive breadth thresholds, not causal/statistical proof.
DIAG_NEIGHBOR_RADIUS = 2
DIAG_MIN_STORE_BASELINE = 25.0
DIAG_MAJOR_DEPT_SHARE = 0.01
DIAG_MIN_POSITIVE_DEPTS = 3
DIAG_MIN_POSITIVE_STORE_FRACTION = 0.50
DIAG_MIN_POSITIVE_DEPT_BASELINE_SHARE = 0.50
DIAG_MAX_TOP_STORE_DELTA_SHARE = 0.25
DIAG_DISPLAY_N = 10
DIAG_FLAGS = ("ZERO_QTY_NONZERO_SALES","NEGATIVE_QUANTITY","NEGATIVE_SALES","POSITIVE_DISCOUNT_VALUE","IS_FREE_ITEM","HAS_LOYALTY_DISC","HAS_COUPON")
DIAG_REPORT_FILE = OUTPUTS_DIR / f"week{DIAG_TARGET_WEEK}_diagnosis.json"
DIAG_VALIDATION_FILE = OUTPUTS_DIR / f"week{DIAG_TARGET_WEEK}_validation.json"
DIAG_TABLE_FILES = {name:f"week{DIAG_TARGET_WEEK}_{name}.csv" for name in ("weekly","department","store","commodity")}
DIAG_CHART_FILE = f"week{DIAG_TARGET_WEEK}_diagnostics.html"
DIAG_MODEL_SOURCE = f"week{DIAG_TARGET_WEEK}_diagnosis.json + validated transactions_master.parquet"
ML_EVALUATION_FILE = OUTPUTS_DIR / "evaluation_ml.json"
ML_EVALUATION_VALIDATION_FILE = OUTPUTS_DIR / "evaluation_ml_validation.json"
SCHEMA_MANIFEST_FILE = OUTPUTS_DIR / "processed_schema_manifest.json"

# Cloud proof settings. Project identity is supplied by the user, never guessed.
CLOUD_TOOLS_DIR = PROJECT_ROOT / ".tools"
CLOUD_CLI_VERSION = "588.0.0"
CLOUD_CLI_ARCHIVE_NAME = f"google-cloud-sdk-{CLOUD_CLI_VERSION}-windows-x86_64-bundled-python.zip"
CLOUD_CLI_ARCHIVE_URL = f"https://dl.google.com/dl/cloudsdk/channels/rapid/downloads/{CLOUD_CLI_ARCHIVE_NAME}"
CLOUD_CLI_ARCHIVE_SHA256 = "9e00e3c9b042f732e29eb7ca6095fdb44bda03938013274a148b5c5f95a6ec92"
CLOUD_CLI_REFERENCE = "https://docs.cloud.google.com/sdk/docs/downloads-versioned-archives"
CLOUD_DOWNLOAD_TIMEOUT = 60
CLOUD_COMMAND_TIMEOUT = 30
CLOUD_GENAI_MODEL = "gemini-3.5-flash"
CLOUD_GENAI_LOCATION = "global"
CLOUD_DEPLOYMENT_REGION = "us-central1"
CLOUD_API_VERSION = "v1"
CLOUD_REQUEST_TIMEOUT_MS = 30000
CLOUD_SMOKE_MAX_TOKENS = 128
CLOUD_SMOKE_PROMPT = "Reply with a brief greeting to confirm that this connection works."
CLOUD_VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
CLOUD_PROJECT_ENV = "GOOGLE_CLOUD_PROJECT"
CLOUD_LOCATION_ENV = "GOOGLE_CLOUD_LOCATION"
CLOUD_MODEL_ENV = "FMCG_GEMINI_MODEL"
CLOUD_PROJECT_PATTERN = r"[a-z][a-z0-9-]{4,28}[a-z0-9]"
CLOUD_PREFLIGHT_FILE = OUTPUTS_DIR / "cloud_preflight.json"
CLOUD_SMOKE_FILE = OUTPUTS_DIR / "vertex_smoke_test.json"



# Conversation limits; these do not change the analytics policy.
CHAT_MAX_INPUT_CHARS = 1500
CHAT_MAX_TURNS = 24
CHAT_MODEL_MAX_TOKENS = 1024
CHAT_STARTERS = ("How are sales doing?", "What should we promote?", "Forecast milk for next month")
CHAT_FOLLOWUPS = ("Short answer", "Explain in detail", "What should I do next?", "Why?", "What are the limitations?")

CHAT_PRESENTATION_VERSION = 3
CHAT_RESPONSE_MODES = ("Short + details", "Detailed")

# User-selected local-only VS Code runtime; no cloud or deployment is required.
LOCAL_ONLY_MODE = True
LOCAL_SERVER_HOST = "127.0.0.1"
LOCAL_SERVER_PORT = 8501


# Review III reporting only; no changes to analytics/model/scope policy.
REVIEW3_SOURCE_FILE = PROJECT_ROOT.parent / "FMCG_Product_Intelligence_System_-_MTech_Review_III-1.pptx"
REVIEW3_OUTPUT_DIR = OUTPUTS_DIR / "review3"
REVIEW3_FILLED_FILE = REVIEW3_OUTPUT_DIR / "FMCG_Review_III_Verified_Local.pptx"
REVIEW3_REPORT_FILE = REVIEW3_OUTPUT_DIR / "review3_report.json"
REVIEW3_VALIDATION_FILE = REVIEW3_OUTPUT_DIR / "review3_validation.json"
REVIEW3_CLIENT_DATE = "2026-10-13"
REVIEW3_BODY_FONT_SIZE = 1800
REVIEW3_METRIC_HORIZON = 1
REVIEW3_TOP_CATEGORY_COUNT = 3
REVIEW3_TOP_DEPARTMENT_COUNT = 3
REVIEW3_RULE_ORDER = ("Frequent recent higher-spend", "Recently active", "Long-gap lower-spend", "Long-gap higher-spend")
