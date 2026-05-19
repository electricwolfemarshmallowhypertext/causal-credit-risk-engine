"""Run public institutional loan-level validation workflow.

This script is a local validation runner for public institutional mortgage datasets.
It does not claim production model validation.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from causal_credit_risk.audit_chain import verify_audit_chain
from causal_credit_risk.batch import run_batch_csv
from causal_credit_risk.cli import run_decision
from causal_credit_risk.cpd_estimation import build_draft_model_config
from causal_credit_risk.fairness import compute_fairness_report
from causal_credit_risk.registry import default_model_config_path, default_policy_config_path
from causal_credit_risk.replay import replay_from_audit_payload
from export_evidence_pack import export_evidence_pack


REQUIRED_NORMALIZED_COLUMNS: tuple[str, ...] = (
    "source_dataset",
    "source_record_id",
    "tenure",
    "utilization",
    "income",
    "dsc",
    "risk",
    "segment",
)


ALLOWED_STATES: dict[str, set[str]] = {
    "tenure": {"short", "long"},
    "utilization": {"low", "high"},
    "income": {"unstable", "stable"},
    "dsc": {"below_threshold", "above_threshold"},
    "risk": {"high_risk", "low_risk"},
}


DATASET_SOURCE_URLS: dict[str, str] = {
    "freddie_mac_sf_loan_level": "https://www.freddiemac.com/research/datasets/sf-loanlevel-dataset",
    "fannie_mae_sf_performance": "https://capitalmarkets.fanniemae.com/credit-risk-transfer/single-family-credit-risk-transfer/fannie-mae-single-family-loan-performance-data",
    "cfpb_hmda": "https://ffiec.cfpb.gov/",
    "fhfa_pudb": "https://www.fhfa.gov/pudbdata",
}


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _read_csv_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if reader.fieldnames is None:
            raise ValueError(f"Missing header row in normalized input: {path}")
        return [dict(row) for row in reader]


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def _validate_and_filter_rows(rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    valid_rows: list[dict[str, str]] = []
    rejected = 0
    for row in rows:
        missing = [column for column in REQUIRED_NORMALIZED_COLUMNS if not row.get(column, "").strip()]
        if missing:
            rejected += 1
            continue

        failed_state = False
        for column, allowed in ALLOWED_STATES.items():
            value = row.get(column, "").strip()
            if value not in allowed:
                failed_state = True
                break
        if failed_state:
            rejected += 1
            continue

        valid_rows.append(row)
    return valid_rows, rejected


def _decision_distribution(batch_rows: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = {"APPROVE": 0, "REVIEW": 0, "DECLINE": 0, "error": 0}
    for row in batch_rows:
        if row.get("status") != "ok":
            counts["error"] += 1
            continue
        decision = row.get("decision", "")
        if decision in counts:
            counts[decision] += 1
        else:
            counts[decision] = 1
    return counts


def _build_validation_report(
    *,
    report_path: Path,
    datasets_used: list[str],
    source_urls: list[str],
    row_count: int,
    rejected_rows: int,
    mapped_fields: list[str],
    cpd_summary: dict[str, Any],
    decision_distribution: dict[str, int],
    replay_success_rate: float,
    audit_chain_valid: bool,
    fairness_summary: dict[str, Any],
    mapping_assumptions: str,
) -> None:
    lines = [
        "# Public Institutional Loan-Level Validation Report",
        "",
        f"Generated: {_utc_now()}",
        "",
        "## Non-production disclaimer",
        "",
        "This report is for public institutional loan-level validation only. "
        "It does not constitute production model validation, credit policy approval, legal advice, or regulatory certification.",
        "",
        "## Dataset used",
        "",
        ", ".join(datasets_used),
        "",
        "## Dataset source URLs",
        "",
    ]
    lines.extend([f"- {url}" for url in source_urls])
    lines.extend(
        [
            "",
            "## Row count",
            "",
            f"- accepted_rows: {row_count}",
            f"- rejected_rows: {rejected_rows}",
            "",
            "## Fields mapped",
            "",
            ", ".join(mapped_fields),
            "",
            "## CPD estimation summary",
            "",
            json.dumps(cpd_summary, indent=2),
            "",
            "## Decision distribution",
            "",
            json.dumps(decision_distribution, indent=2),
            "",
            "## Replay success rate",
            "",
            f"{replay_success_rate:.6f}",
            "",
            "## Audit-chain verification result",
            "",
            str(audit_chain_valid).lower(),
            "",
            "## Fairness diagnostic summary",
            "",
            json.dumps(fairness_summary, indent=2),
            "",
            "## Mapping assumptions",
            "",
            mapping_assumptions,
            "",
            "## Limitations",
            "",
            "- Proxies map mortgage fields into causal engine categories and may not preserve full underwriting context.",
            "- Public datasets have coverage constraints, reporting lags, recodes, and schema changes by year.",
            "- No customer data or PII is used in this workflow.",
            "- This process does not replace independent model-risk, compliance, legal, and fairness governance review.",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run public institutional loan-level validation workflow from normalized inputs."
    )
    parser.add_argument(
        "--normalized-input",
        action="append",
        required=True,
        help="Path to normalized CSV from prepare_* scripts. Repeat for multiple datasets.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "validation" / "outputs" / "public_institutional_validation"),
        help="Directory for validation outputs.",
    )
    parser.add_argument(
        "--model-config",
        default=str(default_model_config_path()),
        help="Base model config for draft CPD estimation.",
    )
    parser.add_argument(
        "--policy-config",
        default=str(default_policy_config_path()),
        help="Policy config path.",
    )
    parser.add_argument(
        "--subgroup-column",
        default="segment",
        help="Subgroup column for fairness diagnostics.",
    )
    parser.add_argument(
        "--max-audits",
        type=int,
        default=100,
        help="Maximum number of decision-level audit traces to generate.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    all_rows: list[dict[str, str]] = []
    datasets_used: list[str] = []
    source_urls: list[str] = []
    for raw_path in args.normalized_input:
        rows = _read_csv_rows(Path(raw_path))
        all_rows.extend(rows)
        dataset_names = sorted({row.get("source_dataset", "") for row in rows if row.get("source_dataset", "")})
        datasets_used.extend(dataset_names)
        for name in dataset_names:
            url = DATASET_SOURCE_URLS.get(name)
            if url:
                source_urls.append(url)

    valid_rows, rejected_rows = _validate_and_filter_rows(all_rows)
    if not valid_rows:
        raise ValueError("No valid normalized rows available after required-field/state filtering.")

    combined_normalized = output_dir / "combined_normalized.csv"
    combined_fields = sorted({key for row in valid_rows for key in row.keys()})
    _write_csv(combined_normalized, combined_fields, valid_rows)

    # 1-2. Estimate draft CPDs from normalized rows.
    cpd_rows = [
        {
            "tenure": row["tenure"],
            "utilization": row["utilization"],
            "income": row["income"],
            "dsc": row["dsc"],
            "risk": row["risk"],
        }
        for row in valid_rows
    ]
    draft_config_payload = build_draft_model_config(
        base_model_config_path=args.model_config,
        rows=cpd_rows,
        source_dataset_reference=";".join(sorted(set(datasets_used))),
        notes="Draft CPD estimate from public institutional loan-level validation inputs.",
    )
    draft_model_config_path = output_dir / "draft_model_config.public_institutional.json"
    draft_model_config_path.write_text(json.dumps(draft_config_payload, indent=2), encoding="utf-8")
    cpd_summary = dict(draft_config_payload.get("estimation_metadata", {}))

    # 3. Run batch decisions from observed evidence.
    batch_input_rows = [
        {
            "tenant_id": row.get("tenant_id", "default"),
            "tenure": row["tenure"],
            "utilization": row["utilization"],
            args.subgroup_column: row.get(args.subgroup_column, "unspecified"),
        }
        for row in valid_rows
    ]
    batch_input_path = output_dir / "batch_input.csv"
    _write_csv(batch_input_path, ["tenant_id", "tenure", "utilization", args.subgroup_column], batch_input_rows)

    batch_output_path = output_dir / "batch_output.csv"
    batch_summary = run_batch_csv(
        model_config_path=draft_model_config_path,
        policy_config_path=args.policy_config,
        csv_input_path=batch_input_path,
        csv_output_path=batch_output_path,
        subgroup_column=args.subgroup_column,
    )

    batch_rows = _read_csv_rows(batch_output_path)
    decision_distribution = _decision_distribution(batch_rows)

    # 4. Fairness diagnostics.
    fairness_report = compute_fairness_report(
        batch_rows,
        subgroup_column=args.subgroup_column,
        min_sample_size=30,
    )
    fairness_path = output_dir / "fairness_report.json"
    fairness_path.write_text(json.dumps(fairness_report, indent=2), encoding="utf-8")

    # 5. Decision-level audit traces and replay checks.
    audit_traces: list[dict[str, Any]] = []
    replay_success = 0
    replay_checked = 0
    for row in valid_rows[: max(args.max_audits, 0)]:
        audit = run_decision(
            model_config_path=draft_model_config_path,
            policy_config_path=args.policy_config,
            evidence={"tenure": row["tenure"], "utilization": row["utilization"]},
            tenant_id=row.get("tenant_id", "default"),
        ).to_dict()
        audit["source_record_id"] = row.get("source_record_id", "")
        audit["source_dataset"] = row.get("source_dataset", "")
        audit_traces.append(audit)

        replay_checked += 1
        replay = replay_from_audit_payload(
            audit_payload=audit,
            model_config_path=draft_model_config_path,
            policy_config_path=args.policy_config,
        )
        if replay.get("risk_probability_match") and replay.get("decision_match"):
            replay_success += 1

    audit_traces_path = output_dir / "audit_traces.json"
    audit_traces_path.write_text(json.dumps(audit_traces, indent=2), encoding="utf-8")
    replay_success_rate = (replay_success / replay_checked) if replay_checked else 0.0

    # 6. Export evidence pack from the batch input.
    evidence_pack_dir = output_dir / "evidence_pack"
    evidence_pack_metadata = export_evidence_pack(
        input_csv=batch_input_path,
        output_dir=evidence_pack_dir,
    )

    audit_chain_path = evidence_pack_dir / "audit_chain.json"
    audit_chain_rows = json.loads(audit_chain_path.read_text(encoding="utf-8"))
    audit_chain_valid = verify_audit_chain(audit_chain_rows)

    # 7. Write validation report.
    report_path = output_dir / "public_institutional_validation_report.generated.md"
    _build_validation_report(
        report_path=report_path,
        datasets_used=sorted(set(datasets_used)),
        source_urls=sorted(set(source_urls)),
        row_count=len(valid_rows),
        rejected_rows=rejected_rows,
        mapped_fields=list(REQUIRED_NORMALIZED_COLUMNS),
        cpd_summary=cpd_summary,
        decision_distribution=decision_distribution,
        replay_success_rate=replay_success_rate,
        audit_chain_valid=audit_chain_valid,
        fairness_summary={
            "subgroup_column": fairness_report.get("subgroup_column"),
            "rows_analyzed": fairness_report.get("rows_analyzed"),
            "max_min_subgroup_delta": fairness_report.get("max_min_subgroup_delta"),
            "warnings": fairness_report.get("warnings"),
        },
        mapping_assumptions=(
            "tenure proxy from loan age; leverage proxy from LTV/CLTV; "
            "affordability proxy from DTI; outcome proxy from delinquency/default or HMDA action_taken."
        ),
    )

    summary = {
        "status": "completed",
        "output_dir": str(output_dir),
        "accepted_rows": len(valid_rows),
        "rejected_rows": rejected_rows,
        "datasets_used": sorted(set(datasets_used)),
        "draft_model_config": str(draft_model_config_path),
        "batch_summary": batch_summary,
        "decision_distribution": decision_distribution,
        "fairness_report": str(fairness_path),
        "audit_traces": str(audit_traces_path),
        "replay_success_rate": replay_success_rate,
        "audit_chain_valid": audit_chain_valid,
        "evidence_pack": evidence_pack_metadata,
        "validation_report": str(report_path),
        "non_production_disclaimer": (
            "Public institutional loan-level validation only. "
            "Not production validation and not a credit eligibility system."
        ),
    }
    summary_path = output_dir / "validation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
