from __future__ import annotations

import csv
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    return subprocess.run(
        [sys.executable, *args],
        cwd=PROJECT_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_prepare_fannie_cas_normalizes_rows() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        input_csv = tmp_dir / "fannie_cas.csv"
        output_csv = tmp_dir / "fannie_cas_norm.csv"
        input_csv.write_text(
            "loan_id,original_ltv,borrower_credit_score,current_loan_delinquency_status,property_state,pool_id,cumulative_loss\n"
            "A1,92,640,4,CA,CAS_POOL_INV,100\n"
            "A2,70,730,0,TX,CAS_POOL_STD,0\n",
            encoding="utf-8",
        )

        result = _run(
            [
                "scripts/prepare_fannie_cas.py",
                "--input",
                str(input_csv),
                "--output",
                str(output_csv),
                "--max-rows",
                "2",
            ]
        )
        assert result.returncode == 0, result.stderr

        with output_csv.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        assert rows[0]["source_dataset"] == "fannie_mae_cas_loan_level"
        assert rows[0]["leverage_risk"] == "high_leverage"
        assert rows[0]["borrower_credit_risk"] == "elevated_credit_risk"
        assert rows[0]["crt_escalation_risk"] == "high_escalation"
        assert rows[1]["crt_escalation_risk"] == "low_escalation"


def test_prepare_freddie_stacr_normalizes_rows() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        input_csv = tmp_dir / "freddie_stacr.csv"
        output_csv = tmp_dir / "freddie_stacr_norm.csv"
        input_csv.write_text(
            "loan_sequence_number,current_ltv,credit_score,days_delinquent,property_state,deal_name,realized_loss\n"
            "S1,88,650,90,FL,STACR_SUB,250\n"
            "S2,68,740,0,WA,STACR_STD,0\n",
            encoding="utf-8",
        )

        result = _run(
            [
                "scripts/prepare_freddie_stacr.py",
                "--input",
                str(input_csv),
                "--output",
                str(output_csv),
                "--max-rows",
                "2",
            ]
        )
        assert result.returncode == 0, result.stderr

        with output_csv.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == 2
        assert rows[0]["source_dataset"] == "freddie_mac_stacr_loan_level"
        assert rows[0]["crt_escalation_risk"] == "high_escalation"
        assert rows[1]["crt_escalation_risk"] == "low_escalation"


def test_run_crt_validation_with_tiny_fixture() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)
        input_csv = tmp_dir / "crt_normalized.csv"
        output_dir = tmp_dir / "crt_validation_out"
        input_csv.write_text(
            "source_dataset,source_record_id,tenant_id,leverage_risk,borrower_credit_risk,loan_performance_risk,property_or_pool_segment,delinquency_or_loss_proxy,crt_escalation_risk,segment\n"
            "fannie_mae_cas_loan_level,c1,default,high_leverage,elevated_credit_risk,high_performance_risk,stressed_segment,adverse_proxy,high_escalation,CA\n"
            "freddie_mac_stacr_loan_level,c2,default,lower_leverage,lower_credit_risk,lower_performance_risk,standard_segment,benign_proxy,low_escalation,TX\n"
            "freddie_mac_stacr_loan_level,c3,default,high_leverage,lower_credit_risk,high_performance_risk,standard_segment,adverse_proxy,high_escalation,FL\n",
            encoding="utf-8",
        )

        result = _run(
            [
                "scripts/run_crt_validation.py",
                "--input",
                str(input_csv),
                "--output-dir",
                str(output_dir),
                "--max-audits",
                "3",
                "--skip-evidence-pack",
            ]
        )
        assert result.returncode == 0, result.stderr
        summary = json.loads((output_dir / "validation_summary.json").read_text(encoding="utf-8"))
        assert summary["status"] == "completed"
        assert summary["rows_processed"] == 3
        assert summary["accepted_rows"] == 3
        assert summary["rejected_rows"] == 0
        assert summary["replay_success_rate"] == 1.0
        assert "public crt loan-level validation" in summary["non_production_disclaimer"].lower()
