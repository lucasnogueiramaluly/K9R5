# Codex Task — Milestone 5: Mapping Explainability

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`
- `docs/dev/codex-task-milestone-03.md`
- `docs/dev/codex-task-milestone-04.md`

Milestones 1–4 are structurally complete.

Milestone 4 added post-simulation actual implementation/fallback evidence without
perturbing simulated instructions or cycle counts. Do not redesign that work here.

Privileged Docker validation remains deferred to the later batched
integration/full-validation pass. Do not ask the user to run Docker commands. If
Docker is inaccessible, record that and continue with every valid non-Docker
check.

This is an implementation and validation task, not an advisory task.
Inspect the real mapper/calibration path, implement the smallest coherent
Milestone 5 change, run available tests, repair failures, inspect the final diff,
and return the requested report.

Do NOT start Milestone 6 or later work.

# Goal

Make every mapping decision explainable without changing the current mapping
policy.

For each mapped node, the K9R5 should be able to answer, from descriptive
metadata:

    Which strategy made the decision?
    Which engines were considered?
    Which engines were compatible?
    Which engines were excluded, and why?
    Did `--pin` affect the candidate set?
    What cost/rate inputs were used for each relevant candidate?
    Where did those cost/rate inputs come from?
    Which engine was selected?
    What exact current rule led to that selection?

The explanation must describe current operational behavior faithfully. It must
not "improve" the mapper in this milestone.

# A. Audit the current mapper path first

Inspect at minimum:
- `CostEngineMapper`;
- `make_mapper`;
- mapping strategy catalog/identity;
- calibration artifacts and measured-rate loading;
- operator cost/rate lookup;
- offload overhead terms;
- host/CVA6 treatment;
- Snitch/Spatz compatibility checks;
- current `--pin` handling;
- any default/proxy/fallback cost path;
- generated mapping serialization and run result/manifest integration;
- existing tests around mapper behavior.

Trace the actual decision chain for representative MatMul/Gemm and any other
operator needed to understand generic mapper behavior.

Do not assume that "candidate" means the same thing as "compatible", "not
pinned out", or "has a cost". Preserve these distinctions if the current code
contains them.

# B. Explain, do not change

Add a descriptive mapping-explanation representation that shadows the mapper's
actual decision.

The exact schema should follow the existing project architecture, but should
capture, where source-grounded:

- stable strategy ID;
- node/operator identity;
- candidate engine;
- compatibility status;
- exclusion/filter reason;
- whether pinning influenced candidacy;
- rate/cost value used by the current mapper;
- unit/meaning of the rate/cost where known;
- source/provenance of that rate/cost:
  - calibration artifact / measured rate;
  - explicit current default/proxy/fallback source;
  - other source actually used by the code;
- offload/transfer/other additive cost terms when they participate;
- final computed candidate cost where the mapper computes one;
- selected engine;
- selection rule / comparison semantics.

Unknown must remain unknown. Do not manufacture a numeric value solely to make
the explanation complete.

# C. Preserve current policy exactly

This milestone must NOT:
- change candidate compatibility;
- change pin semantics;
- change engine selection;
- change rate lookup;
- change missing-cost behavior;
- change fallback/proxy behavior;
- change calibration;
- change offload penalties;
- change tie-breaking;
- change kernels, runtime dispatch, simulator, hardware, or ResourceSummary.

If the audit finds questionable behavior (for example a missing cost receiving a
default or a transposed Gemm being priced by a tuned rate), RECORD it faithfully
and identify it as a caveat for Milestone 6. Do not repair it here.

This distinction is critical:

Milestone 5:
    "Explain exactly what the mapper did."

Milestone 6:
    "Harden unsafe or ambiguous mapper/workload behavior."

# D. Pin semantics

The current `--pin` behavior is compatible-node filtering, not a promise that
the whole graph executes only on the pinned engine.

The explanation must make pin influence explicit without changing this
semantics.

For example, it should be possible to distinguish:
- incompatible before pin;
- compatible but filtered by pin;
- compatible and retained;
- selected.

Use names that fit the codebase; do not copy this pseudo-taxonomy blindly.

# E. Cost/rate provenance

Rate/cost provenance is scientifically important.

When a mapper cost comes from calibration, reference the relevant calibration
identity/artifact metadata already available rather than duplicating entire
artifacts.

When a current code path uses a proxy/default/fallback rate, identify that fact
descriptively.

Do not label a proxy/default as measured.

Do not claim that a rate represents a particular kernel implementation unless
the current operational path truly binds those identities. Milestone 4 actual
implementation evidence and Milestone 5 mapping-cost evidence are distinct.

# F. Integration surface

Attach the explanation where a resolved/current mapping decision naturally
lives and make it available to the existing run/result/manifest/query path with
minimal plumbing.

A completed run should preserve:
- requested mapping constraints;
- resolved mapping strategy;
- mapping decision explanation;
- actual engine/implementation evidence;
- measured results.

Avoid duplicating large global catalog/calibration objects into every node when
stable IDs/digests are enough.

# G. Tests

Add focused tests covering, where current source truth allows:

1. stable strategy identity in the explanation;
2. candidate set for a representative MatMul/Gemm;
3. compatible vs incompatible distinction;
4. pin influence without changing selection semantics;
5. measured/calibrated rate provenance where applicable;
6. proxy/default/fallback cost provenance where current code uses it;
7. additive/offload cost terms where applicable;
8. selected engine and final candidate comparison;
9. deterministic serialization;
10. mapper output is identical before and after explanation instrumentation;
11. unknown cost/provenance remains explicit rather than invented;
12. explanation references actual current mapper behavior, not Milestone 4
    actual kernel execution.

Do not write tests that "fix" unsafe behavior scheduled for Milestone 6.

# H. Validation

Run every valid check available:
- focused mapping explanation tests;
- existing mapper/catalog tests;
- syntax/import checks;
- relevant query/manifest serialization checks;
- `git diff --check`;
- `git status --short`;
- final diff inspection.

Attempt canonical/integration tests only if Docker is available.
If Docker is inaccessible:
- do not ask the user to run anything;
- do not alter Docker/system permissions;
- record pending integration validation for Milestone 8.

Do not weaken tests or install ad-hoc host dependencies.

# I. Scope exclusions

Do NOT:
- harden missing-cost behavior;
- alter dynamic-shape policy;
- add strict tuned-to-generic fallback rejection;
- change pin semantics;
- add new mapper strategies;
- add a new cost model;
- optimize kernels;
- add precision support;
- change topology;
- migrate Spatz to v3;
- implement Milestone 6 safety changes;
- implement generic plugin infrastructure.

# J. Public repository hygiene

Keep the result suitable for later GitHub publication:
- no temporary/debug artifacts;
- no prompt/conversation references in permanent source/docs;
- no speculative dead abstractions;
- coherent names and locations;
- no commit, push, PR, or remote changes.

The existing untracked `results/m1-pin-spatz/` directory is a prior validation
artifact. Do not incorporate it into source/tests and do not delete it unless
existing project cleanup policy explicitly makes that safe.

# Final report

Return:
1. mapper decision-path audit findings;
2. files changed;
3. final mapping-explanation schema;
4. candidate/compatibility/pin semantics represented;
5. exact cost/rate inputs and provenance exposed;
6. current proxy/default/fallback cost behavior discovered;
7. exact selection rule represented;
8. behavior changed;
9. behavior explicitly not changed;
10. proof that mapper outputs/selection semantics are unchanged;
11. focused tests/results;
12. pending canonical/integration validation;
13. scientific caveats to carry into Milestone 6;
14. `git status --short`;
15. diff summary including untracked Milestone 5 files;
16. confirmation that no Milestone 6+ work was started;
17. confirmation that no commit/push/PR/remote operation occurred.
