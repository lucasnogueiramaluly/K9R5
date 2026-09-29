# Codex Task — Milestone 2: ResourceSummary

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`

Milestone 1 is closed and validated:
- canonical Python suite: 60/60 passing;
- real pinned Spatz sweep: status `ok`;
- MatMul actually executed on Spatz;
- `pin=spatz` was preserved in request, resolved mapping metadata, and actual mapping;
- no mapper semantics were changed.

One validation observation must remain visible for later work:
- a real run manifest reported `provenance.k9r5.available = false` with reason
  `git-metadata-unavailable` inside the runtime/container environment.
This is NOT part of Milestone 2. Do not fix it here. Preserve it as a known later validation/provenance issue.

This is an implementation and validation task, not an advisory task.
Do not stop after proposing a design. Inspect the actual source, implement the
smallest coherent Milestone 2 change, run the available tests, repair failures,
inspect the diff, and finish with the requested report.

Do NOT start Milestone 3 or later work.

# Goal

Add a descriptive `ResourceSummary` layer that makes the resources represented
by a resolved K9R5 hardware configuration explicit enough for controlled
experimental comparison.

This layer must describe existing operational truth. It must NOT become a new
source of hardware configuration truth and must NOT change simulator, runtime,
mapping, kernel, build, or calibration behavior.

The scientific purpose is to prevent shorthand such as:

    "9 cores vs 9 cores"

from being silently interpreted as:

    equi-compute
    equi-FPU
    equi-area
    equi-power
    same-memory-system

# A. Audit before designing

Inspect the current implementation and operational sources before choosing the
exact schema or module location.

At minimum inspect:

- `pipeline/experiment/schema.py`
- `pipeline/experiment/catalog.py` and related catalog modules
- `pipeline/experiment/resolve.py`
- serialization used for `ResolvedExperiment`
- `pipeline/gui_query.py`
- current parameter/design validation
- `pipeline/run_hetero.py`
- `pipeline/hetero_platform/`
- `targets/hetero/`
- runtime code that determines which cores actually perform compute
- legacy Snitch/Spatz GVSoC construction used by K9R5
- tests under `pipeline/tests/`

Determine from source, rather than assumption:

- total modeled cores for Snitch and Spatz;
- which core(s) are reserved for control/DMA/non-compute work;
- how many cores are actually used by the current runtime for compute;
- whether every modeled Spatz core physically receives a VPU;
- lanes per Spatz PE and how they are parameterized;
- whether a defensible physical/useful lane or FPU count can be derived;
- TCDM size;
- TCDM bank count only where the current operational model makes it explicit;
- any memory-path/port fact that is safely derivable without inventing
  architectural equivalence.

Do not copy values from this prompt when the code disagrees. Operational source
wins.

# B. Implement the smallest coherent ResourceSummary

Follow the existing project architecture and naming conventions.

Prefer a derived descriptive object attached to the resolved experiment rather
than another operational configuration system.

The exact data model may be adapted to the existing schema, but it should be
able to express, when safely known:

- physical/modelled core count;
- compute PE/core count;
- control/DMA/non-compute core count;
- lanes per compute PE where applicable;
- useful arithmetic lane/FPU count where defensible;
- physical arithmetic lane/FPU count only if the model really instantiates it
  and the distinction is meaningful;
- TCDM size;
- TCDM bank count where known;
- other directly supported resource facts that materially help normalize
  experiments.

Unknown facts must stay unknown/absent. Do not convert uncertainty to zero.

Do NOT add area, power, frequency, or "equivalent compute" estimates unless the
repository has a concrete operational source for them.

Do NOT introduce arbitrary "area units", scores, fairness labels, or
architecture rankings.

# C. Precision / peak-throughput caution

A nominal FP32 throughput field is optional, not required.

Only expose nominal peak arithmetic throughput if all of the following can be
supported from current operational/model sources:

1. the arithmetic width/packing semantics are explicit;
2. the number of active arithmetic resources is defensible;
3. the metric can be named with unambiguous units;
4. it is clearly labelled nominal/theoretical, not measured.

If any of these are uncertain, omit the peak field in this milestone.

Do not infer scientific superiority from it.

# D. Required semantics

ResourceSummary must preserve at least these distinctions where the source
supports them:

- modeled/physical resources vs resources actually useful to current compute;
- Snitch vs Spatz resource shape;
- core/PE count vs Spatz lane count;
- compute core(s) vs control/DMA core(s);
- configured TCDM capacity vs assumptions about bandwidth;
- known resource values vs unknown values.

Changing a real design knob such as `SNITCH_NB_CORE`, `SPATZ_NB_CORE`,
`SPATZ_NB_LANES`, or `TCDM_SIZE` must change the derived summary in the expected
causal way.

ResourceSummary must be deterministic for the same resolved design.

# E. Integration surface

Expose ResourceSummary in the resolved experiment in the smallest natural way
supported by the existing schema.

It should therefore be available to downstream manifest/sweep/GUI metadata
through the existing resolved-experiment serialization path without duplicating
manual plumbing unless required.

Do not change operational hardware defaults or mapper behavior.

If `gui_query resolve-experiment` serializes `ResolvedExperiment`, verify that
the resources appear there.

Do not add a new GUI framework or generic plugin mechanism.

# F. Tests

Add focused tests that verify source-grounded resource semantics.

At minimum cover:

1. baseline/default resolved resource summary;
2. Snitch compute count changes causally with `SNITCH_NB_CORE`;
3. Spatz compute count changes causally with `SPATZ_NB_CORE`;
4. Spatz lane/resource count changes causally with `SPATZ_NB_LANES`;
5. TCDM size is derived from the resolved design;
6. unknown/unavailable facts remain unknown rather than becoming zero;
7. ResourceSummary serialization is deterministic;
8. existing resolved experiment behavior remains otherwise unchanged.

Where the runtime reserves a final control/DMA core, include a regression test
that prevents future metadata from silently treating that reserved core as
useful compute.

Where physical and useful Spatz arithmetic-resource counts differ, test the
distinction only if the source audit proves it.

Do not write a test for an architectural claim that the implementation cannot
actually establish.

# G. Validation

The Codex environment may not have Docker permission.

Do not weaken tests because host Python lacks dependencies.
Do not install packages into host Python just to make tests pass.

Run everything that is valid in the available environment:

- focused tests;
- syntax/import checks as appropriate;
- `git diff --check`;
- `git status --short`;
- final diff inspection.

Attempt the canonical suite only if the canonical environment is available.

If Docker remains inaccessible, return the exact minimal `sudo docker exec`
commands I should run manually for:
- the full `make python-test`;
- one resolved-experiment query showing baseline ResourceSummary;
- one overridden configuration showing that the summary changes causally.

Do not modify Docker permissions, groups, sudoers, or machine configuration.

# H. Public repository hygiene

Keep this suitable for later GitHub publication:

- no temporary/debug artifacts;
- no prompt/conversation references in permanent code or docs;
- no dead speculative abstractions;
- names should make sense to another researcher reading the repository;
- every new file must have a coherent project location;
- leave the worktree suitable for one clean reviewable milestone commit, but do
  NOT commit, push, open a PR, or change remotes.

# Final report

Return:

1. source audit findings used to derive the summary;
2. files changed;
3. final ResourceSummary schema/shape;
4. which facts are known and which deliberately remain unknown;
5. exact behavior changed;
6. behavior explicitly not changed;
7. focused tests and results;
8. canonical/manual validation still required, if any;
9. any scientific caveats;
10. `git diff --stat`;
11. confirmation that no Milestone 3+ work was started;
12. confirmation that no commit/push/PR/remote operation occurred.

Do not proceed to KernelImplementation.
