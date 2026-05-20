"""Normalize HMDA public data into engine-compatible validation CSV."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from public_mortgage_validation_common import (
    first_value,
    normalize_header,
    normalized_record,
    write_normalized_csv,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare HMDA public institutional validation input.")
    parser.add_argument("--input", required=True, help="Path to HMDA CSV file")
    parser.add_argument(
        "--output",
        default=str(ROOT / "validation" / "outputs" / "hmda_normalized.csv"),
        help="Normalized output CSV path",
    )
    parser.add_argument(
        "--delimiter",
        default="auto",
        help="Input delimiter (use 'auto' to detect from header line)",
    )
    parser.add_argument("--encoding", default="utf-8-sig", help="Input encoding")
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional maximum number of rows to normalize.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    input_path = Path(args.input)
    with input_path.open("r", encoding=args.encoding, newline="") as fh:
        header_line = fh.readline()
    delimiter = args.delimiter
    if delimiter == "auto":
        delimiter = "|" if header_line.count("|") > header_line.count(",") else ","

    normalized_rows: list[dict[str, str]] = []
    with input_path.open("r", encoding=args.encoding, newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        if reader.fieldnames is None:
            raise ValueError(f"HMDA input is missing a header row: {input_path}")
        normalized_headers = [normalize_header(name) for name in reader.fieldnames]

        for idx, row in enumerate(reader, start=1):
            raw = {
                normalized_headers[col_idx]: str(value).strip()
                for col_idx, value in enumerate(row.values())
                if col_idx < len(normalized_headers)
            }
            record_id = (
                first_value(raw, ("lei", "loan_id", "respondent_id"))
                or f"hmda_{idx}"
            )
            normalized = normalized_record(
                source_dataset="cfpb_hmda",
                source_record_id=record_id,
                row=raw,
            )

            # HMDA-specific demographic aliases.
            normalized["race"] = (
                first_value(
                    raw,
                    (
                        "applicant_race_1",
                        "race_of_applicant_or_borrower_1",
                        "derived_race",
                    ),
                )
                or normalized["race"]
            )
            normalized["sex"] = (
                first_value(
                    raw,
                    (
                        "applicant_sex",
                        "sex_of_applicant_or_borrower",
                        "derived_sex",
                    ),
                )
                or normalized["sex"]
            )
            normalized["income_amount"] = (
                first_value(raw, ("income", "income_amount", "applicant_income_000s"))
                or normalized["income_amount"]
            )
            normalized["geography_state"] = (
                first_value(raw, ("state", "state_2", "state_3", "state_code"))
                or normalized["geography_state"]
            )
            normalized["geography_county"] = (
                first_value(raw, ("county", "county_code"))
                or normalized["geography_county"]
            )
            normalized["geography_tract"] = (
                first_value(raw, ("census_tract", "tract"))
                or normalized["geography_tract"]
            )
            normalized_rows.append(normalized)
            if args.max_rows is not None and idx >= args.max_rows:
                break

    write_normalized_csv(args.output, normalized_rows)
    print(f"prepared_rows={len(normalized_rows)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
