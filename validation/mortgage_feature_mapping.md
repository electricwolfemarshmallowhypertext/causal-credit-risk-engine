# Mortgage Feature Mapping

This document records transformation assumptions from source datasets into causal engine variables.

## Target engine variables

- `tenure` -> observed node (`short`/`long`)
- `utilization` -> observed node (`low`/`high`)
- `income` -> inferred-node proxy (`unstable`/`stable`)
- `dsc` -> inferred-node proxy (`below_threshold`/`above_threshold`)
- `risk` -> outcome proxy (`high_risk`/`low_risk`)
- `segment` -> subgroup identifier for fairness diagnostics

## Mapping assumptions (current implementation)

1. `tenure` proxy:
   - Source preference: `loan_age`, `loan_age_months`, `age_of_mortgage_note`.
   - Rule: `loan_age >= 24` months -> `long`, else `short`.

2. `utilization` proxy:
   - Source preference: CLTV/LTV aliases.
   - Rule: `LTV_or_CLTV >= 80` -> `high`, else `low`.

3. `income` proxy:
   - Source preference: credit score aliases.
   - Rule: `credit_score >= 680` -> `stable`, else `unstable`.

4. `dsc` proxy:
   - Source preference: DTI aliases.
   - Rule: `DTI >= 43` -> `below_threshold`, else `above_threshold`.

5. `risk` proxy:
   - Source preference: delinquency/default fields.
   - Rule examples:
     - delinquency status code in `RA/REO/FC/F/D` -> `high_risk`
     - numeric delinquency bucket `>=3` -> `high_risk`
     - otherwise `low_risk`
   - HMDA fallback:
     - `action_taken` in `{3,7}` -> `high_risk`
     - `action_taken` in `{1,2,6,8}` -> `low_risk`

## Source-field alias coverage

Scripts use alias-based lookup to handle naming variation across releases and file layouts.

- Freddie / Fannie focus: origination LTV/CLTV/DTI/credit score + monthly delinquency/loan age.
- HMDA focus: action taken, DTI/CLTV where reported, demographics/geography fields.
- FHFA PUDB focus: income/race/sex/tract/LTV/mortgage age/affordability-related fields.

## Required documentation in generated reports

Generated validation reports must state:

- dataset source
- mapping assumptions
- known limitations
- non-production disclaimer

## Non-production warning

These mappings are proxies for **public institutional loan-level validation**. They are not full underwriting transformations and are not production decision rules.
