# P2.2 local sensitivity implementation plan

Implement `docs/superpowers/specs/2026-11-03-p2-local-sensitivity-design.md` on `codex/p2-local-sensitivity`, based on P2.1.

1. Add analytic, axis, perturbation-bound, aggregate-budget, and failure-context tests first; confirm the new API is missing.
2. Add immutable result serialization and central finite differences using the existing RK4 solver. Keep perturbation sizes caller-specified and preflight work before RHS calls.
3. Document assumptions, numerical error sources, in-process callback boundary, and the fact this does not establish identifiability or scientific validity.
4. Run sensitivity and solver regression suites, structural skill validation, review the diff, record evidence, then commit and open a separate draft PR targeting P2.1. Do not merge or release.
