# P2.4 observation/residual bridge evidence

**State:** local verification and independent review complete; branch CI pending. The real SIR case is `NOT_RUN` because no equations or data were supplied.

## Implemented

`ObservationDataset.from_dict` accepts schema v1 with an explicitly ordered variable list and units, increasing finite observation times, sparse value rows, and provenance requiring a `source`. It produces a canonical SHA-256 content digest that includes variable order; a supplied digest is verified. Construction is restricted to the validated factory, and nested values are immutable. The digest identifies serialized content and does not authenticate source metadata.

`evaluate_observations` checks model time/state names and exact unit matches before the RHS runs. It splits fixed-step RK4 integration at each observation time, so irregular times need no interpolation. It preflights per-interval and total step budgets before simulation and returns observed/simulated values plus deterministic residual ordering for direct use by `fit_least_squares`.

## Verification performed

| Environment | Command | Result |
|---|---|---|
| Windows, local Python 3.14.0 | `python -m unittest tests.test_scientific_observations tests.test_scientific_optimization tests.test_scientific_sensitivity tests.test_scientific_core -q` | PASS, 50 tests |
| Docker/Linux, `python:3.14.0-bookworm` | Same unittest command | PASS, 50 tests |
| Windows, local Python 3.14.0 | `python -m py_compile scripts/scientific_core.py tests/test_scientific_observations.py` | PASS |
| Windows, local Python 3.14.0 | `git diff --check` | PASS |

Coverage includes hash round-trip through sorted JSON, mutation isolation, disabled unvalidated construction, schema errors, sparse rows, explicit order and matching digest, exact irregular-time sampling, unit/name/time-range checks, preflight budgets with zero RHS calls on failure, and composition through RK4 into least-squares fitting on synthetic decay data.

## Interpretation and limits

- Residuals are raw, unweighted `simulated - observed` differences. A joint squared-error objective across variables with unlike units is not meaningful until the caller applies justified scales or weights. No scales are inferred.
- Units must match exactly. There is no unit conversion, interpolation, imputation, CSV reader, weighting, uncertainty model, or data-cleaning policy.
- Segmented fixed-step RK4 does not estimate local or global error, enforce positivity/invariants, or establish model validity.
- The source metadata is user-declared. The digest detects content changes; it is not a signature or provenance verification.
- No modified SIR equations or experimental data were provided; SIR-specific simulation/fitting/audit is `NOT_RUN`.
- Independent review found and led to fixes for digest/order mismatch and constructor bypass; the final read-only review found no additional important findings. The 3.11/3.12 branch CI matrix is pending.

## Next increment

Continue with a reusable scientific workspace contract only when it is needed for the SIR end-to-end case. The equations, parameter definitions, initial conditions, units, and observations must come from the user; no domain-specific template is inferred here.
