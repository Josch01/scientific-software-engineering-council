# P2.4 observation and residual contract

## Intent

Provide a generic, versioned bridge from experimental observations to the existing RK4 simulator and least-squares optimizer. No SIR equations or measurements were supplied, so the implementation must not encode epidemiological assumptions.

## Contract

- `ObservationDataset.from_dict` validates schema v1: explicit time unit, an ordered list of named variables with units, strictly increasing finite observation times, finite values keyed by observed variable, and non-empty provenance containing `source`.
- Sparse measurements are represented by omitting unobserved variables from a row. Every row must contain at least one measurement. Duplicate/unknown fields, unknown variables, malformed units/provenance, non-finite values, oversized payloads, and unsupported schema versions fail explicitly.
- Canonical JSON produces a SHA-256 digest for content identity, including variable/residual order. A supplied digest is verified. This detects content mismatch; it does not authenticate the source. The validated dataset can only be created with `from_dict`, so direct construction cannot bypass freezing or hash checks.
- `evaluate_observations(problem, dataset, ...)` verifies time/state names and units before executing the RHS. It integrates separately to each exact observation time using the existing fixed-step RK4 solver, so irregular times do not require interpolation. Segment step counts are preflighted against per-segment and total budgets before any RHS call.
- Residual order is deterministic: observation times in input order, then variables in the explicit list order. Residual is the raw, unweighted simulated minus observed difference. The immutable result records observed/simulated values, residual order, source provenance, dataset digest, model parameters/units, segment step sizes, and work counts. Before fitting a joint objective across variables with unlike units, the caller must scale or weight residuals; no such weighting is inferred.
- Callers can pass `result.residuals` directly to `fit_least_squares`; model construction stays with the caller.

## Limits

There is no CSV importer, missing-value imputation, interpolation, weighting, uncertainty model, unit conversion, or SIR-specific logic. Units must match exactly. The content digest is not proof of provenance. RK4 is fixed-step and does not estimate error. This bridge validates software contracts, not scientific validity.

## Acceptance

- Round-trip a versioned sparse observation set and verify stable content digest.
- Reject malformed, non-finite, inconsistent, oversized, or unit-incompatible inputs before RHS work.
- Evaluate irregular observation times exactly with bounded segmented RK4 and deterministic residual order.
- Reject insufficient work budgets before the first RHS call.
- Compose observations → RK4 → residuals → least-squares fitting on synthetic data.
- Preserve existing solver/optimizer behavior and add no dependencies.
