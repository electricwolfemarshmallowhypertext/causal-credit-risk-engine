# Public CRT Loan-Level Validation Report

Generated: pending local run

## Non-production disclaimer

Public CRT loan-level validation. Not production validation, not consumer credit eligibility, and not regulatory compliance proof.

## Scope

This report captures C-DAG validation runs over local public credit risk transfer (CRT) disclosure inputs:

- Fannie Mae CAS-style loan-level disclosure files
- Freddie Mac STACR-style loan-level disclosure files

## Required outputs for each run

- rows processed
- accepted/rejected rows
- dataset source
- mapped fields
- decision distribution
- replay success rate
- audit-chain verification
- sampled evidence pack mode
- limitations

## Standard mapped variables

- `leverage_risk`
- `borrower_credit_risk`
- `loan_performance_risk`
- `property_or_pool_segment`
- `delinquency_or_loss_proxy`
- `crt_escalation_risk`
- `segment`
- `source_dataset`

## Limitations

- Mapping rules are proxy transformations from public disclosure fields.
- This workflow is for explainability/governance validation and replayability checks.
- It does not establish production model suitability or legal/regulatory certification.
