"""Normalize FHFA PUDB files into engine-compatible validation CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from public_mortgage_validation_common import (
    first_value,
    normalized_record,
    read_delimited_rows,
    write_normalized_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare FHFA PUDB validation input.")
    parser.add_argument("--input", required=True, help="Path to FHFA PUDB file")
    parser.add_argument(
        "--output",
        default=str(ROOT / "validation" / "outputs" / "fhfa_normalized.csv"),
        help="Normalized output CSV path",
    )
    parser.add_argument("--delimiter", default=",", help="Input delimiter")
    parser.add_argument("--encoding", default="utf-8-sig", help="Input encoding")
    parser.add_argument(
        "--no-header",
        action="store_true",
        help="Disable header parsing (not supported in this lightweight parser).",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.no_header:
        raise ValueError("FHFA preparation currently requires header-based CSV input.")
    rows = read_delimited_rows(
        input_path=args.input,
        delimiter=args.delimiter,
        has_header=True,
        fieldnames=None,
        encoding=args.encoding,
    )

    normalized_rows: list[dict[str, str]] = []
    for idx, raw in enumerate(rows, start=1):
        record_id = first_value(raw, ("loan_id", "record_id", "loan_sequence_number")) or f"fhfa_{idx}"
        normalized = normalized_record(
            source_dataset="fhfa_pudb",
            source_record_id=record_id,
            row=raw,
        )
        normalized["race"] = (
            first_value(raw, ("race", "borrower_race")) or normalized["race"]
        )
        normalized["sex"] = (
            first_value(raw, ("sex", "borrower_sex")) or normalized["sex"]
        )
        normalized["income_amount"] = (
            first_value(raw, ("income", "borrower_income")) or normalized["income_amount"]
        )
        normalized["geography_tract"] = (
            first_value(raw, ("census_tract", "tract")) or normalized["geography_tract"]
        )
        normalized_rows.append(normalized)

    write_normalized_csv(args.output, normalized_rows)
    print(f"prepared_rows={len(normalized_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
