# Public Institutional Loan-Level Validation Report

Generated: 2026-05-19T20:10:09+00:00

## Non-production disclaimer

This report is for **public institutional loan-level validation** only. It is not production model validation, not a lending decision system, and not legal or regulatory certification.

## Dataset scope used in this run

- Freddie Mac normalized loan-level sample: `50,000` rows
- HMDA normalized sample: `50,000` rows
- Combined rows processed: `100,000`
- Fannie Mae performance/acquisition files: not present in local `examples/data/FannieMae` at run time

HMDA rows are used for decision-disparity/fairness diagnostics. CPD estimation in this run is restricted to performance-oriented source datasets (Freddie/Fannie/FHFA), and only Freddie rows were available.

## Mapped-variable distributions

### Freddie Mac normalized rows (50,000)

- tenure proxy (`tenure`): `long=41,421`, `short=8,579`
- leverage proxy (`utilization`): `high=26,130`, `low=23,870`
- stability proxy (`income`): `stable=46,401`, `unstable=3,599`
- affordability proxy (`dsc`): `below_threshold=12,035`, `above_threshold=37,965`
- outcome proxy (`risk`): `high_risk=227`, `low_risk=49,773`
- top segments: `CA=8,068`, `TX=3,551`, `FL=3,223`, `CO=2,072`, `IL=2,056`

### HMDA normalized rows (50,000)

- tenure proxy (`tenure`): `short=50,000`
- leverage proxy (`utilization`): `high=49,574`, `low=426`
- stability proxy (`income`): `unstable=50,000`
- affordability proxy (`dsc`): `below_threshold=49,672`, `above_threshold=328`
- outcome proxy (`risk`): `high_risk=430`, `low_risk=49,570`
- top segments: `7|4=48,482`, `5|1=721`, `5|2=351`, `6|3=133`, `6|1=72`

### Combined normalized rows (100,000)

- tenure: `long=41,421`, `short=58,579`
- utilization: `high=75,704`, `low=24,296`
- income: `stable=46,401`, `unstable=53,599`
- dsc: `below_threshold=61,707`, `above_threshold=38,293`
- risk proxy: `high_risk=657`, `low_risk=99,343`

## Original run result (calibration issue observed)

Original mixed-data run output:

- decision distribution: `APPROVE=100,000`, `REVIEW=0`, `DECLINE=0`
- risk probability range: `min=0.005620`, `max=0.018831`
- unique risk levels (rounded): `0.005620`, `0.006441`, `0.009378`, `0.018831`

Why this happened:

- The default reference policy thresholds (`review 0.35-0.5`, `decline >=0.5`) are demo thresholds tuned for the reference toy model, not for low-prevalence public institutional outcome proxies.
- Public normalized outcome-proxy prevalence in this run is low (`657/100,000 = 0.657%` high-risk proxy), producing low posterior risk values that never cross default demo thresholds.

## Corrected public-validation model/policy

Separate configs were created and used:

- model config: `configs/public_mortgage_model.v1.json`
- policy config: `configs/public_mortgage_policy.v1.json`

Design intent:

- keep reference demo model/config behavior unchanged
- calibrate a separate policy range for public institutional loan-level validation outputs
- keep HMDA usage for fairness/decision-disparity diagnostics rather than default-performance claims

## Corrected run result

Run: `validation/outputs/public_institutional_validation_publiccfg_20260519_100k`

- accepted rows: `100,000`
- rejected rows: `0`
- decision distribution: `APPROVE=24,296`, `REVIEW=21,929`, `DECLINE=53,775`
- replay success rate: `1.000000`
- audit-chain verification: `true`

## Fairness diagnostics summary

- subgroup column: `segment`
- rows analyzed: `100,000`
- max/min subgroup deltas:
  - `mean_risk_probability_delta=0.000397`
  - `approve_rate_delta=0.800000`
  - `decline_rate_delta=1.000000`
- small-sample subgroup warnings were emitted for low-count groups (for example `PR`, `GU`, `VI`).

Fairness diagnostics are descriptive only and not fairness certification.

## Limitations

- Proxies map institutional mortgage fields into coarse causal-engine states; they do not represent full underwriting logic.
- Outcome mapping is proxy-based (delinquency/action-taken driven), not adjudicated default labels across a complete credit lifecycle.
- HMDA fields are application/action oriented and should not be treated as a default-performance ground truth source.
- Fannie Mae and FHFA files were not available in this local run input set.
- This workflow does not replace model-risk governance, legal review, compliance review, fairness validation, or production monitoring.
