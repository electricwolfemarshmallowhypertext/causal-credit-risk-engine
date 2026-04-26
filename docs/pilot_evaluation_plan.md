# Pilot Evaluation Plan

## Pilot objective

This pilot evaluates whether `causal-credit-risk-engine` can support model-risk, compliance, internal audit, or AI governance workflows by producing replayable causal audit artifacts from controlled decision inputs.

The pilot is not a production deployment, credit approval workflow, legal compliance review, or fairness certification. It is a structured evaluation of causal traceability, deterministic replay, audit-chain integrity, subgroup diagnostics, and evidence-pack usefulness.

## Duration

2 to 4 weeks.

## Pilot structure

1. Week 1: environment setup, config review, demo baseline.
2. Week 2: batch/replay/fairness workflow validation.
3. Week 3: governance evidence-pack review with model-risk/compliance.
4. Optional Week 4: integration readiness decision.

## Success criteria

- Deterministic replay passes for selected decisions.
- Batch workflow produces row-level explainability artifacts.
- Fairness diagnostics generate subgroup metrics and warnings.
- Audit chain verification detects tampering.
- Governance teams can review artifacts without code changes.

## Technical validation

- API and CLI parity checks.
- Input validation failure-path checks.
- Config/version contract checks.
- Smoke tests and unit tests reviewed.

## Governance validation

- Model and policy version traceability.
- Counterfactual interpretability review.
- Audit artifact completeness review.
- Limitations and prohibited-use acknowledgment.

## Sample artifacts delivered

- Decision audit JSON
- Replay result JSON
- Fairness report JSON
- Audit chain JSON + verification result
- Evidence-pack metadata manifest

## Out of scope

- Legal sign-off
- Production credit policy approval
- Fairness certification
- Hosted infrastructure and SSO rollout

## Decision criteria for paid license

## Commercial transition

A paid commercial license is required before any production deployment, regulated workflow use, customer-data validation, internal system integration, or customer-facing use.

A commercial pilot or production license may include:

- integration guidance
- deployment-boundary review
- configuration review
- audit-output review
- evidence-pack workflow review
- governance documentation support
- adapter planning for auth, storage, tenancy, model registry, or policy registry

Commercial support does not include legal advice, credit-policy approval, fairness certification, adverse-action review, or certified regulatory compliance.

For commercial licensing, contact: smith@antiparty.co

- Pilot success criteria met.
- Integration scope agreed.
- Commercial terms and support boundary accepted.
