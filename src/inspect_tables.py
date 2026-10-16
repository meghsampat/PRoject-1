"""Inspect all eight CSV files in chunks. Run: python src/inspect_tables.py."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import pandas as pd
from src import config
from src.artifact_io import file_fingerprint, write_json


def main():
    results = []
    for name in config.SOURCE_CSV_FILES:
        path = config.PROJECT_ROOT / name
        rows, missing = 0, None
        dtypes = None
        for chunk in pd.read_csv(path, chunksize=config.CSV_CHUNK_ROWS):
            rows += len(chunk)
            counts = chunk.isna().sum()
            missing = counts if missing is None else missing.add(counts, fill_value=0)
            if dtypes is None:
                dtypes = {column: str(dtype) for column, dtype in chunk.dtypes.items()}
        result = {**file_fingerprint(path), "rows": int(rows), "columns": list(dtypes or {}), "first_chunk_dtypes": dtypes, "missing_values": {} if missing is None else {column: int(value) for column, value in missing.items()}}
        results.append(result)
        print(f"Inspected {name}: {rows:,} rows", flush=True)
    report = {"status": "INSPECTED", "tables": results, "note": "Full row/null counts and SHA-256 hashes. First-chunk types do not prove every value is valid. Join, calendar and money checks are performed by master validation."}
    write_json(config.OUTPUTS_DIR / "source_inspection.json", report)
    print("Saved outputs/source_inspection.json", flush=True)


if __name__ == "__main__":
    main()
