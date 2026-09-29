# Codex Task — Milestone 4: Actual Kernel Implementation + Fallback Tracking

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`
- `docs/dev/codex-task-milestone-03.md`

Milestones 1–3 are structurally complete.
Milestone 3 established a descriptive inventory of available kernel paths:
- `cva6.fp32.matmul_gemm.deeploy_generic`
- `snitch.fp32.matmul_gemm.ssr_frep`
- `snitch.fp32.matmul_gemm.deeploy_generic_fallback`
- `spatz.fp32.matmul_gemm.rvv_tuned`
- `spatz.fp32.matmul_gemm.deeploy_generic_fallback`

Important source-audit facts from Milestone 3:
- Generic public symbols are renamed to `<symbol>_generic` when overridden.
- `cluster_main.c` dispatches FP32 MatMul/Gemm to the public symbols.
- Snitch SSR/FREP falls back to Generic for empty dimensions or `O < 8`;
  non-multiple-of-8 columns use a scalar tail inside the tuned implementation.
- Spatz hand-written RVV falls back to Generic for empty dimensions and, for
  GEMM, transpose cases.
- Host-mapped nodes use Deeploy Generic symbols directly.

Privileged Docker validation is deferred to the later batched integration/full
validation pass. Do not ask the user to run Docker commands. If Docker is
inaccessible, record that and continue with all valid non-Docker checks.

This is an implementation task. Inspect the repository, implement the smallest
coherent Milestone 4 change, run available tests, repair failures, inspect the
final diff, and return the requested report.

Do NOT start Milestone 5 or later work.

# Goal

Make each completed heterogeneous run report, as part of its `actual` state,
which kernel implementation actually handled each relevant node and whether the
execution used a fallback.

The scientific contract is:

    requested -> resolved -> actual -> measured

Milestone 3 catalogued what implementations exist.
Milestone 4 must connect a real completed run to the implementation path that
actually handled it, without silently guessing.

# A. Audit the evidence path before implementing

Inspect how a run currently produces:
- mapping metadata;
- generated model/operator metadata;
- runtime kernel arguments;
- node-level result/progress information;
- `result.json`;
- `manifest.json`;
- any runtime stdout/stderr/progress parsing.

Also inspect the exact branch conditions inside the Snitch and Spatz tuned
MatMul/Gemm implementations and how generic fallback is invoked.

Determine the least invasive way to establish actual implementation identity.

Prefer evidence already available at execution time.
If exact implementation identity can be deterministically resolved from actual
runtime arguments and exact compiled/selected kernel path, that may be used,
but the metadata MUST state the evidence type and MUST NOT pretend it was
runtime-reported.

Do not infer actual implementation merely from:
- mapper choice;
- logical engine;
- catalog availability;
- requested pin;
- a predicted cost-model path.

# B. Evidence semantics

Represent implementation identity with an explicit evidence/provenance concept.
The exact schema may follow project conventions, but it must distinguish at
least:

- implementation ID;
- fallback used: true / false / unknown;
- fallback from implementation ID when applicable;
- fallback to implementation ID when applicable;
- fallback reason when known from exact branch conditions;
- evidence type/source.

Examples of acceptable evidence categories:
- runtime-reported;
- deterministically resolved from actual runtime arguments + exact compiled
  dispatch path;
- unavailable/unknown.

Use names appropriate to the codebase; do not add these literal strings if a
better existing convention exists.

Unknown must remain unknown. Never encode unknown as false or as a generic
implementation guess.

# C. Required current behavior

For current FP32 MatMul/Gemm paths, track as much as source truth allows:

1. CVA6/host Generic execution.
2. Snitch tuned SSR/FREP execution when its compatibility path is taken.
3. Snitch fallback to Deeploy Generic for the exact fallback conditions proved
   by source.
4. Spatz tuned RVV execution when its compatibility path is taken.
5. Spatz fallback to Deeploy Generic for the exact fallback conditions proved
   by source.

Important:
- Snitch scalar tail for non-multiple-of-8 columns is part of the tuned
  implementation, not a whole-kernel Generic fallback unless the source proves
  otherwise.
- Do not generalize a MatMul condition to Gemm or vice versa unless source
  proves it.
- Do not represent the legacy single-core `--spatz-kernels autovec` path as
  actual hetero execution unless `run_hetero.py` can really produce it.

# D. Where the metadata belongs

Attach actual implementation/fallback identity to the existing node-level
`actual` execution representation in the smallest natural way.

A real run manifest should make it possible to answer:

    node N:
      engine = spatz
      implementation = spatz.fp32.matmul_gemm.rvv_tuned
      fallback = false
      evidence = ...

or, when the fallback branch was taken:

    node N:
      engine = spatz
      implementation = spatz.fp32.matmul_gemm.deeploy_generic_fallback
      fallback = true
      fallback_from = spatz.fp32.matmul_gemm.rvv_tuned
      reason = <source-grounded reason>
      evidence = ...

Use the actual project schema rather than copying this pseudo-shape verbatim.

Do not duplicate the Milestone 3 catalog into every run. Runs should reference
stable implementation IDs and only carry actual-run evidence/details needed for
reproducibility.

# E. Preserve measurement validity

Do not add instrumentation that materially changes simulated cycle counts merely
to report an implementation ID if a non-perturbing or post-run deterministic
evidence path exists.

If runtime instrumentation is unavoidable, explain:
- why;
- whether it changes modeled instructions/cycles;
- how measurement validity is preserved.

Prefer a design that does not perturb the kernel hot path.

Do not modify performance kernels just to add logging unless no safer evidence
path exists.

# F. Fallback semantics

A fallback event must be explicit and source-grounded.

The system must distinguish:
- tuned implementation executed normally;
- tuned implementation executed with an internal scalar tail;
- whole-kernel fallback to Generic;
- actual implementation unavailable/unknown.

Do not treat:
- scalar tail,
- mapper selecting CVA6,
- unsupported engine,
- pin filtering

as kernel fallback unless that is what the runtime implementation actually does.

# G. Tests

Add focused tests that cover, where source truth allows:

1. tuned Snitch MatMul/Gemm identity;
2. Snitch Generic fallback identity and exact reason;
3. tuned Spatz MatMul/Gemm identity;
4. Spatz Generic fallback identity and exact reason;
5. CVA6 Generic identity;
6. Snitch scalar-tail case remains tuned rather than being mislabeled fallback;
7. unknown/unsupported evidence remains unknown;
8. stable implementation IDs reference Milestone 3 catalog entries;
9. node-level actual serialization carries implementation/fallback evidence;
10. existing mapper choice, result cycles, and measurement schema remain
    otherwise unchanged.

Prefer unit tests that do not require GVSoC for branch/evidence resolution.
Do not fabricate runtime observations in tests without clearly testing the
resolver/parser layer.

# H. Validation

Run every valid check available:
- focused tests;
- syntax/import checks;
- relevant manifest/result serialization checks;
- existing catalog/discovery tests;
- `git diff --check`;
- `git status --short`;
- final diff inspection.

Attempt canonical/integration tests only if Docker is available.
If Docker is unavailable:
- do not ask the user to run anything;
- do not alter Docker/system permissions;
- record the pending integration validation for Milestone 8.

Do not weaken tests or install ad-hoc host dependencies.

# I. Scope exclusions

Do NOT:
- change mapper policy or cost model;
- change kernel selection behavior;
- optimize kernels;
- change hardware configuration;
- change ResourceSummary semantics;
- migrate Spatz to v3;
- implement Mapping Explainability (Milestone 5);
- implement generic strict-fallback policy (Milestone 6);
- add new precision support;
- add tiling/double buffering/new scheduling.

# J. Public repository hygiene

Keep the result suitable for later GitHub publication:
- no temporary/debug artifacts;
- no prompt/conversation references in permanent project code/docs;
- no speculative abstractions;
- coherent names and locations;
- no commit, push, PR, or remote changes.

The existing untracked `results/m1-pin-spatz/` directory is a prior validation
artifact. Do not incorporate it into source code or tests. Do not delete it
unless existing project cleanup policy explicitly makes that safe.

# Final report

Return:
1. actual-evidence audit findings;
2. exact mechanism used to determine actual implementation;
3. files changed;
4. actual implementation/fallback schema;
5. evidence types and semantics;
6. tracked current implementation/fallback cases;
7. known vs deliberately unknown cases;
8. whether measurement/cycle behavior is perturbed;
9. behavior changed;
10. behavior explicitly not changed;
11. focused tests/results;
12. pending canonical/integration validation;
13. scientific caveats;
14. `git status --short`;
15. diff summary including untracked Milestone 4 files;
16. confirmation that no Milestone 5+ work was started;
17. confirmation that no commit/push/PR/remote operation occurred.
