"""Export a local evidence pack for pilot governance review."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from causal_credit_risk.audit_chain import build_audit_chain_record, verify_audit_chain
from causal_credit_risk.batch import run_batch_csv
from causal_credit_risk.cli import run_decision
from causal_credit_risk.fairness import compute_fairness_report
from causal_credit_risk.registry import default_model_config_path, default_policy_config_path
from causal_credit_risk.replay import replay_from_audit_payload


def _utc_stamp() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _progress(message: str) -> None:
    print(f"[progress] {message}", file=sys.stderr, flush=True)


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"Missing CSV headers: {path}")
        return [dict(row) for row in reader]


def export_evidence_pack(
    *,
    input_csv: Path,
    output_dir: Path,
    model_config_path: Path | None = None,
    policy_config_path: Path | None = None,
    max_rows: int | None = None,
) -> dict[str, Any]:
    model_path = model_config_path or default_model_config_path()
    policy_path = policy_config_path or default_policy_config_path()
    output_dir.mkdir(parents=True, exist_ok=True)

    _progress("loading evidence-pack input")
    batch_output = output_dir / "batch_output.csv"
    source_rows = _read_csv(input_csv)
    if max_rows is not None:
        if max_rows <= 0:
            raise ValueError("max_rows must be a positive integer")
        source_rows = source_rows[:max_rows]
    if not source_rows:
        raise ValueError("Evidence-pack input contains no rows")

    source_csv_for_batch = input_csv
    if max_rows is not None:
        sample_input = output_dir / "evidence_pack_input.sampled.csv"
        fieldnames = list(source_rows[0].keys())
        with sample_input.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(source_rows)
        source_csv_for_batch = sample_input

    subgroup = "segment" if source_rows and "segment" in source_rows[0] else None

    _progress("running evidence-pack batch decisions")
    batch_summary = run_batch_csv(
        model_config_path=model_path,
        policy_config_path=policy_path,
        csv_input_path=source_csv_for_batch,
        csv_output_path=batch_output,
        subgroup_column=subgroup,
    )

    _progress("generating evidence-pack fairness report")
    batch_rows = _read_csv(batch_output)
    fairness_report = compute_fairness_report(
        batch_rows,
        subgroup_column=subgroup or "segment",
        min_sample_size=2,
    )
    fairness_path = output_dir / "fairness_report.json"
    fairness_path.write_text(json.dumps(fairness_report, indent=2), encoding="utf-8")

    _progress("generating evidence-pack audit chain")
    chain_records: list[dict[str, Any]] = []
    previous_hash: str | None = None
    for index, row in enumerate(source_rows):
        evidence = {k: v for k, v in row.items() if k in {"tenure", "utilization"}}
        tenant_id = str(row.get("tenant_id", "default")).strip() or "default"
        audit = run_decision(
            model_config_path=model_path,
            policy_config_path=policy_path,
            evidence=evidence,
            tenant_id=tenant_id,
        ).to_dict()
        chain_record = build_audit_chain_record(
            audit,
            chain_index=index,
            previous_hash=previous_hash,
            tenant_id=tenant_id,
        )
        chain_records.append(chain_record)
        previous_hash = str(chain_record["audit_hash"])

    chain_path = output_dir / "audit_chain.json"
    chain_path.write_text(json.dumps(chain_records, indent=2), encoding="utf-8")
    chain_valid = verify_audit_chain(chain_records)
    chain_verify_path = output_dir / "audit_chain_verify.json"
    chain_verify_path.write_text(
        json.dumps({"valid": chain_valid, "records_checked": len(chain_records)}, indent=2),
        encoding="utf-8",
    )

    replay_result = replay_from_audit_payload(
        audit_payload=chain_records[0]["audit_record"],
        model_config_path=model_path,
        policy_config_path=policy_path,
    )
    replay_path = output_dir / "replay_result.json"
    replay_path.write_text(json.dumps(replay_result, indent=2), encoding="utf-8")

    model_copy = output_dir / model_path.name
    policy_copy = output_dir / policy_path.name
    shutil.copy2(model_path, model_copy)
    shutil.copy2(policy_path, policy_copy)

    metadata = {
        "generated_at_utc": datetime.now(tz=timezone.utc).isoformat(timespec="seconds"),
        "input_csv": str(input_csv),
        "input_rows_used": len(source_rows),
        "max_rows": max_rows,
        "batch_output": str(batch_output),
        "fairness_report": str(fairness_path),
        "audit_chain": str(chain_path),
        "audit_chain_verification": str(chain_verify_path),
        "replay_result": str(replay_path),
        "model_config_copy": str(model_copy),
        "policy_config_copy": str(policy_copy),
    }
    metadata_path = output_dir / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return metadata


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a local governance evidence pack.")
    parser.add_argument(
        "--input-csv",
        default="examples/batch_with_segments.csv",
        help="Batch input CSV path",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory. Defaults to outputs/evidence_pack_<timestamp>/",
    )
    parser.add_argument(
        "--model-config",
        default=None,
        help="Optional model config path. Defaults to reference model config.",
    )
    parser.add_argument(
        "--policy-config",
        default=None,
        help="Optional policy config path. Defaults to reference policy config.",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=None,
        help="Optional maximum number of input rows to include in the evidence pack.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    root = ROOT
    input_csv = Path(args.input_csv)
    if not input_csv.is_absolute():
        input_csv = root / input_csv
    if not input_csv.exists():
        parser.error(f"Input CSV not found: {input_csv}")

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else root / "outputs" / f"evidence_pack_{_utc_stamp()}"
    )
    if not output_dir.is_absolute():
        output_dir = root / output_dir

    model_config_path: Path | None = None
    if args.model_config:
        model_config_path = Path(args.model_config)
        if not model_config_path.is_absolute():
            model_config_path = root / model_config_path
        if not model_config_path.exists():
            parser.error(f"Model config not found: {model_config_path}")

    policy_config_path: Path | None = None
    if args.policy_config:
        policy_config_path = Path(args.policy_config)
        if not policy_config_path.is_absolute():
            policy_config_path = root / policy_config_path
        if not policy_config_path.exists():
            parser.error(f"Policy config not found: {policy_config_path}")

    metadata = export_evidence_pack(
        input_csv=input_csv,
        output_dir=output_dir,
        model_config_path=model_config_path,
        policy_config_path=policy_config_path,
        max_rows=args.max_rows,
    )
    print(json.dumps(metadata, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
