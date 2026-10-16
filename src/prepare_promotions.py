"""Chunked raw promotion preparation. Analysis subsequently reads only processed files."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from collections import Counter
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_processed_master, load_validated_aggregate
from src.promotion_support import KEYS, summarize_matches
from src.scope import policy_fingerprint


def main():
    config.PROMOTION_VALIDATION_FILE.unlink(missing_ok=True)
    source = file_fingerprint(config.CAUSAL_FILE)
    master = load_processed_master(require_scope=True)
    window = master.loc[master.IN_SCOPE & config.in_analysis_window(master) & master.IS_COMPLETE_WEEK]
    matches = window.groupby(KEYS, sort=True).agg(COMMODITY_DESC=("COMMODITY_DESC", "first"),
                                                 revenue=("SALES_VALUE", "sum")).reset_index()
    index = pd.MultiIndex.from_frame(matches[KEYS])
    display = np.zeros(len(matches), dtype=np.uint16)
    mailer = np.zeros(len(matches), dtype=np.uint16)
    source_records = np.zeros(len(matches), dtype=np.int64)
    counts_display, counts_mailer = Counter(), Counter()
    rows = 0
    dmap = {code: 1 << i for i, code in enumerate(config.DISPLAY_CODES)}
    mmap = {code: 1 << i for i, code in enumerate(config.MAILER_CODES)}
    for chunk in pd.read_csv(config.CAUSAL_FILE, chunksize=config.CSV_CHUNK_ROWS,
                             dtype={"display": "str", "mailer": "str"}):
        if chunk[KEYS + ["display", "mailer"]].isna().any().any():
            raise ValueError("Missing promotion keys/codes; no rows silently dropped.")
        if any(not np.isfinite(chunk[key]).all() or (chunk[key] % 1 != 0).any() for key in KEYS):
            raise ValueError("Promotion keys must be finite integers.")
        counts_display.update(chunk.display.value_counts().to_dict())
        counts_mailer.update(chunk.mailer.value_counts().to_dict())
        if not chunk.display.isin(dmap).all() or not chunk.mailer.isin(mmap).all():
            raise ValueError("Unrecognized display/mailer code; review reference before preparation.")
        positions = index.get_indexer(pd.MultiIndex.from_frame(chunk[KEYS]))
        found = positions >= 0
        pos = positions[found]
        np.bitwise_or.at(display, pos, chunk.loc[found, "display"].map(dmap).to_numpy(dtype=np.uint16))
        np.bitwise_or.at(mailer, pos, chunk.loc[found, "mailer"].map(mmap).to_numpy(dtype=np.uint16))
        np.add.at(source_records, pos, 1)
        rows += len(chunk)
        if rows % (config.CSV_CHUNK_ROWS * config.PROMO_PROGRESS_CHUNKS) == 0:
            print(f"Scanned {rows:,} promotion rows; matched {(display > 0).sum():,} observed sales keys", flush=True)
    if file_fingerprint(config.CAUSAL_FILE) != source:
        raise ValueError("Promotion source changed during preparation.")
    matches["display_mask"] = display
    matches["mailer_mask"] = mailer
    matches["source_records"] = source_records
    weekly = load_validated_aggregate("commodity_weekly")
    grid = weekly.loc[weekly.in_window, ["COMMODITY_DESC", "WEEK_NO"]]
    exposure = summarize_matches(matches, grid)
    paths = [config.PROCESSED_DIR / f"{name}.parquet" for name in config.PROMOTION_TABLES]
    for frame, path in zip([matches, exposure], paths):
        frame.to_parquet(path, index=False, compression=config.PARQUET_COMPRESSION)
    write_json(config.PROMOTION_BUILD_FILE, {
        "status": "BUILT_REQUIRES_VALIDATION", "policy_fingerprint": policy_fingerprint(),
        "master_sha256": file_fingerprint(config.MASTER_FILE)["sha256"],
        "weekly_sha256": file_fingerprint(config.PROCESSED_DIR / "commodity_weekly.parquet")["sha256"],
        "source": source, "source_rows": rows, "display_codes": dict(counts_display),
        "mailer_codes": dict(counts_mailer), "extra_matched_records_combined": int(source_records.sum() - (source_records > 0).sum()),
        "multiple_record_sales_keys": int((source_records > 1).sum()),
        "observed_sales_keys": len(matches), "matched_sales_keys": int((display > 0).sum()),
        "coverage_share": float((display > 0).mean()),
        "start_week": int(window.WEEK_NO.min()), "end_week": int(window.WEEK_NO.max()),
        "settings": {"display_codes": config.DISPLAY_CODES, "mailer_codes": config.MAILER_CODES},
        "artifacts": [file_fingerprint(path) for path in paths],
        "reference": config.PROMOTION_CODE_REFERENCE,
        "note": "Denominator: observed sold product/store/week keys. Missing records are unknown; shares use matched keys. Multiple source records are combined by any nonzero display/mailer; exact code sets retained as bit masks in config code order. Each observed sales key contributes once. Associations condition on sold assortment and are not causal effects."
    })
    print(f"Prepared promotion exposures: {rows:,} raw rows, {(display > 0).mean():.2%} sales-key coverage. Run src/validate_promotions.py.", flush=True)


if __name__ == "__main__":
    main()
