# Codex Task — Milestone 3: KernelImplementation Catalog

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`

Milestone 1 is closed.
Milestone 2 is implemented and structurally reviewed. Its focused tests passed.
Privileged Docker validation for Milestone 2 is deferred to the later batched
integration/full-validation pass and must not block this milestone.

Do not ask the user to run Docker commands during this milestone. If Docker is
unavailable from your environment, record canonical integration validation as
pending and continue with every valid non-Docker check.

This is an implementation and validation task, not an advisory task.
Do not stop after proposing a design. Inspect the actual repository, implement
the smallest coherent Milestone 3 change, run available tests, repair failures,
inspect the final diff, and return the requested report.

Do NOT start Milestone 4 or later work.

# Goal

Add a descriptive `KernelImplementation` catalog for kernel implementations
that actually exist in the current K9R5 software paths.

The catalog must answer:

    "Which implementation paths exist, and how does the current software reach them?"

It must NOT yet answer:

    "Which implementation actually executed in this particular run?"

Actual per-run implementation/fallback tracking belongs to Milestone 4.

# A. Audit operational truth first

Trace the current source-to-runtime path before defining stable IDs.

Audit at minimum:
- current MatMul/Gemm paths for Snitch;
- current MatMul/Gemm paths for Spatz;
- relevant CVA6/generic paths when they materially participate in fallback or
  dispatch;
- Deeploy integration/overrides;
- runtime sources;
- build macros/overrides;
- generated/runtime dispatch;
- generic fallback paths;
- any shape/layout/transposition conditions that are explicit in source.

Follow the actual chain where possible:

    source file
    -> function/symbol
    -> build-time selection/override
    -> generated/runtime dispatch
    -> compatibility conditions
    -> fallback path

Do not copy remembered names or assumptions from previous discussion when the
repository disagrees. Operational source wins.

# B. Catalog semantics

For each implementation, record only defensible facts such as:
- stable implementation ID;
- logical engine (`cva6`, `snitch`, `spatz`);
- operator(s)/workload class implemented;
- source file;
- function/symbol where explicit;
- build-time selector/override mechanism;
- runtime dispatch mechanism;
- explicit compatibility conditions;
- known fallback target/path;
- classification such as tuned/specialized, compiler-autovectorized, generic,
  scalar, RVV, SSR/FREP only when source proves that description.

Unknown/ambiguous facts must remain unknown/ambiguous.

Do not use the catalog as a new operational source of kernel selection truth.
It should shadow and describe existing behavior.

# C. Scientific constraints

Do not:
- claim an implementation executed in a specific run;
- infer performance from implementation identity;
- rank implementations;
- change mapper behavior;
- change kernel code;
- change runtime dispatch;
- change simulator behavior;
- change calibration;
- change hardware defaults;
- change pin semantics;
- change ResourceSummary;
- migrate Spatz to v3;
- start run-manifest implementation tracking;
- start fallback tracking beyond descriptive catalog relationships.

The key distinction must remain:

Milestone 3:
    available implementation inventory

Milestone 4:
    actual implementation + fallback evidence per run

# D. Stable identity and drift resistance

Use stable IDs that are meaningful to future researchers and survive harmless
path/layout refactors where practical.

Prefer consistency/drift checks against operational source where possible.
Examples:
- source file or symbol existence;
- known selector macro/value;
- operator/engine coverage;
- fallback target existence.

Do not overfit tests to incidental formatting.

# E. Integration surface

Expose the catalog through the existing experiment/catalog/query architecture in
the smallest natural way.

If current GUI/query discovery has a catalog/schema surface, integrate there
rather than inventing a parallel interface.

Do not change resolved-run semantics except for descriptive discovery metadata
where naturally appropriate.

# F. Tests

Add focused tests covering:
1. stable implementation IDs;
2. expected current Snitch MatMul/Gemm implementation entries;
3. expected current Spatz MatMul/Gemm implementation entries;
4. source/symbol/selector drift checks where defensible;
5. explicit known fallback relationships;
6. unknown facts remain unknown rather than guessed;
7. catalog serialization/query is deterministic;
8. existing mapper/runtime behavior is unchanged.

Do not write tests for claims the source audit cannot establish.

# G. Validation

Run every valid check available in your environment:
- focused tests;
- syntax/import checks;
- relevant discovery/query checks;
- `git diff --check`;
- `git status --short`;
- final diff inspection.

Attempt the canonical suite only if the canonical environment is available.

If Docker is inaccessible:
- do NOT ask the user to run manual commands;
- do NOT change Docker/system permissions;
- simply record canonical integration validation as pending for the later
  batched full-validation pass.

Do not weaken tests or install ad-hoc host dependencies merely to force the host
suite to pass.

# H. Public repository hygiene

Keep the result suitable for later GitHub publication:
- no temporary/debug artifacts;
- no prompt/conversation references in permanent project code/docs;
- no speculative dead abstractions;
- coherent names and locations;
- no commit, push, PR, or remote changes.

# Final report

Return:
1. source-to-runtime audit findings;
2. exact implementations discovered;
3. files changed;
4. catalog schema and stable IDs;
5. known vs deliberately unknown facts;
6. fallback relationships discovered from source;
7. exact behavior changed;
8. behavior explicitly not changed;
9. focused tests and results;
10. canonical/integration validation still pending, if any;
11. scientific caveats;
12. `git status --short`;
13. a diff summary that includes untracked Milestone 3 files;
14. confirmation that no Milestone 4+ work was started;
15. confirmation that no commit/push/PR/remote operation occurred.
