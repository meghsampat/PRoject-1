"""Independent promotion/source reconciliation; raw access is preparation validation only."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import json
import numpy as np
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json
from src.data_access import load_processed_master, load_validated_aggregate
from src.promotion_support import KEYS
from src.scope import policy_fingerprint


def main():
    report = json.loads(config.PROMOTION_BUILD_FILE.read_text(encoding="utf-8"))
    assert report["policy_fingerprint"] == policy_fingerprint()
    assert report["master_sha256"] == file_fingerprint(config.MASTER_FILE)["sha256"]
    assert report["source"] == file_fingerprint(config.CAUSAL_FILE)
    for item in report["artifacts"]:
        assert item == file_fingerprint(config.PROCESSED_DIR / item["name"])
    matches = pd.read_parquet(config.PROCESSED_DIR / "promotion_sales_keys.parquet")
    exposure = pd.read_parquet(config.PROCESSED_DIR / "promo_category_weekly.parquet")
    master = load_processed_master()
    window = master.loc[master.IN_SCOPE & config.in_analysis_window(master) & master.IS_COMPLETE_WEEK]
    direct = window.groupby(KEYS).agg(COMMODITY_DESC=("COMMODITY_DESC", "first"), revenue=("SALES_VALUE", "sum")).reset_index()
    pd.testing.assert_frame_equal(matches[direct.columns], direct, check_dtype=False)
    assert matches.source_records.gt(0).equals(matches.display_mask.gt(0))
    assert matches.source_records.gt(0).equals(matches.mailer_mask.gt(0))
    index = pd.MultiIndex.from_frame(matches[KEYS])
    seen = np.zeros(len(matches), dtype=bool)
    dy_seen, my_seen = seen.copy(), seen.copy()
    record_counts = np.zeros(len(matches), dtype=np.int64)
    rows = 0
    for chunk in pd.read_csv(config.CAUSAL_FILE, chunksize=config.CSV_CHUNK_ROWS, dtype={"display": "str", "mailer": "str"}):
        positions = index.get_indexer(pd.MultiIndex.from_frame(chunk[KEYS]))
        found = positions >= 0
        selected = matches.iloc[positions[found]]
        d = chunk.loc[found, "display"]
        m = chunk.loc[found, "mailer"]
        dbits = d.map({code: 1 << i for i, code in enumerate(config.DISPLAY_CODES)}).to_numpy(dtype=np.uint16)
        mbits = m.map({code: 1 << i for i, code in enumerate(config.MAILER_CODES)}).to_numpy(dtype=np.uint16)
        assert ((selected.display_mask.to_numpy() & dbits) == dbits).all()
        assert ((selected.mailer_mask.to_numpy() & mbits) == mbits).all()
        np.logical_or.at(dy_seen, positions[found], d.ne("0").to_numpy())
        np.logical_or.at(my_seen, positions[found], m.ne("0").to_numpy())
        np.add.at(record_counts, positions[found], 1)
        seen[positions[found]] = True
        rows += len(chunk)
        if rows % (config.CSV_CHUNK_ROWS * config.PROMO_PROGRESS_CHUNKS) == 0:
            print(f"Validated {rows:,} source promotion rows", flush=True)
    assert np.array_equal(seen, matches.source_records.gt(0))
    assert np.array_equal(dy_seen, matches.display_mask.gt(1))
    assert np.array_equal(my_seen, matches.mailer_mask.gt(1))
    assert np.array_equal(record_counts, matches.source_records)
    assert rows == report["source_rows"]
    assert seen.sum() == report["matched_sales_keys"]
    expected = {}
    for (category, week), g in matches.groupby(["COMMODITY_DESC", "WEEK_NO"]):
        known = g.source_records.gt(0)
        dy, my = g.display_mask.gt(1), g.mailer_mask.gt(1)
        expected[(category, week)] = (len(g), int(known.sum()), int(dy.sum()), int(my.sum()), int((dy | my).sum()))
    weekly = load_validated_aggregate("commodity_weekly")
    grid = weekly.loc[weekly.in_window, ["COMMODITY_DESC", "WEEK_NO"]].reset_index(drop=True)
    pd.testing.assert_frame_equal(exposure[grid.columns], grid, check_dtype=False)
    for row in exposure.itertuples():
        counts = expected.get((row.COMMODITY_DESC, row.WEEK_NO), (0, 0, 0, 0, 0))
        assert counts == (row.sales_keys, row.matched_keys, row.display_keys, row.mailer_keys, row.any_promo_keys)
        assert np.isclose(row.coverage_share, counts[1] / counts[0] if counts[0] else np.nan, equal_nan=True)
        for numerator, label in zip(counts[2:], ["display", "mailer", "any_promo"]):
            assert np.isclose(getattr(row, label + "_share"), numerator / counts[1] if counts[1] else np.nan, equal_nan=True)
    assert report["source"] == file_fingerprint(config.CAUSAL_FILE)
    write_json(config.PROMOTION_VALIDATION_FILE, {"status": "PASS",
        "build_report_sha256": file_fingerprint(config.PROMOTION_BUILD_FILE)["sha256"],
        "checks": ["Every processed sales key/category/revenue reconciles with approved complete-week master",
                   "All 36M+ raw promotion rows scanned; every matched code and missing-key status reproduced",
                   "One key one vote; category/week counts and unknown denominators independently reconcile"],
        "source_rows": rows, "matched_sales_keys": int(seen.sum()), "coverage_share": float(seen.mean())})
    print("PASS: independent promotion preparation validation", flush=True)


if __name__ == "__main__":
    main()
