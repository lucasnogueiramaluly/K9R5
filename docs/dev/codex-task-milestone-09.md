# Codex Task — Milestone 9: Run Identity and Provenance Hardening

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`
- `docs/dev/extension-seams.md`
- `docs/dev/codex-task-milestone-08.md`

Current frozen base for this task:

```text
branch: lucas-ic
commit: 45bbb7da05b1df139f03ebf098ffcc2d751262ee
message: Freeze experimental foundation M1-M8
upstream base: 6d40999f244c038f882c5746381f35d565432dcc
```

Milestones 1–8 are frozen. This task is a narrowly scoped hardening pass before
Phase B architectural experiments.

Do NOT begin Phase B.

Do NOT commit, push, open a PR, reset, clean, rebase, or change remotes.

Do NOT modify `results/mnist-hetero.json`, `results/m1-pin-spatz/`, or `AGENTS.md`
unless the user explicitly asks later.

# Goal

Close four specific audit gaps without changing simulated execution:

1. separate `actual` from `measured` in the run manifest;
2. give a workload a stable whole-package identity in addition to its ONNX digest;
3. add run-specific source provenance independent of calibration provenance;
4. centralize the Python interpretation of MatMul/Gemm implementation/fallback rules.

The resulting contract should be closer to:

```text
REQUESTED
what was asked for
        ↓
RESOLVED
complete deterministic configuration
        ↓
ACTUAL
what mapping / implementation / fallback actually executed
        ↓
MEASURED
cycles, correctness, accuracy, error, wall time, counters
```

while preserving all existing execution behavior.

---

# A. Start with an audit, not edits

Before changing files, inspect the current implementation at `45bbb7d`.

At minimum read:

```text
pipeline/experiment/schema.py
pipeline/experiment/workload.py
pipeline/experiment/fingerprint.py
pipeline/experiment/provenance.py
pipeline/experiment/calibration_artifact.py
pipeline/experiment/run_manifest.py
pipeline/experiment/actual_implementation.py
pipeline/experiment/kernel_implementation_catalog.py

pipeline/hetero_platform/mapper.py
pipeline/hetero_platform/generate.py
pipeline/hetero_platform/engines.py

pipeline/run_hetero.py
pipeline/sweep/run.py
pipeline/sweep/design.py
pipeline/sweep/calibrate.py

pipeline/common.py
pipeline/build_mesh.py
pipeline/gen_system_header.py

runtime/mesh/hes_host.c
runtime/mesh/cluster_main.c
runtime/snitch/kernels/gemm_fp32_ssr.c
runtime/spatz/kernels/gemm_fp32_rvv.c

targets/hetero/system.py
targets/hetero/soc.py
```

Also inspect all current tests under `pipeline/tests/` that cover these surfaces.

Before editing, summarize internally:
- current manifest shape;
- current workload identity;
- current calibration provenance;
- current run provenance;
- all duplicated MatMul/Gemm fallback rules;
- compatibility constraints for existing result files.

Do not assume the task description is correct if the source contradicts it.

---

# B. Requirement 1 — first-class `measured` manifest section

## Problem

The conceptual model is:

```text
request -> resolved -> actual -> measured
```

but the current manifest API stores:

```text
request
resolved
actual
```

and sweep code places the runtime `result` object inside `actual`.

That makes measured observations structurally part of actual execution state.

## Required change

New manifests must have four explicit first-class sections:

```json
{
  "request": {},
  "resolved": {},
  "actual": {},
  "measured": {}
}
```

### `actual`

Keep facts about what executed, such as:
- mapping;
- engine selected per node;
- implementation ID;
- fallback evidence;
- actual runtime/dispatch identity that is not itself a measurement.

### `measured`

Put observations here, such as:
- cycles;
- per-node cycles;
- per-engine cycles;
- correctness;
- `maxdiff`;
- accuracy / agreement;
- offload failures;
- cache counters;
- wall time;
- application-level measured metrics.

Do not invent a taxonomy where the current result does not contain one.

## Compatibility

Do not change the shape of existing `result.json` files written by
`run_hetero.py` merely to satisfy this task.

Prefer changing the manifest construction boundary.

If a current reader genuinely requires `actual.result`, preserve compatibility
through an explicit reader/normalization path where practical rather than
persisting two independent copies that can drift.

If a stored compatibility alias is unavoidable, it must be generated from one
canonical value and tested for equality.

Add or bump an explicit manifest schema/version identifier if the current code
has a suitable versioning mechanism. Do not invent a large migration framework.

---

# C. Requirement 2 — whole-workload identity

## Problem

The current workload content digest identifies `network.onnx`, but execution
also depends on workload-side files such as test inputs / expected outputs and,
for current application workloads, their evaluation data header.

The ONNX digest remains useful and must not silently change meaning.

## Required change

Preserve the existing ONNX content digest semantics.

Add a distinct whole-workload identity, for example:

```text
workload_fingerprint
artifact_digests
```

or an equivalent clear structure.

The fingerprint must be deterministic and path-location independent.

### Generic op package

Audit the actual generation path and include the workload artifacts that
causally affect the current run. For the current Generic op layout this is
expected to include, when present and actually used:

```text
network.onnx
inputs.npz
outputs.npz
```

Do not hash every file in the directory.

### Current application workloads

Use the repository's existing application detection / metadata rather than
creating a second application registry.

If the current run consumes an application-specific evaluation artifact such as:

```text
mnist_data.h
kws_data.h
```

include that actual consumed artifact in the workload package fingerprint.

Do not include:
- logs;
- generated work directories;
- result JSONs;
- caches;
- unrelated documentation;
- arbitrary files merely because they are in the same directory.

### Representation

Record each included artifact with:
- repo/workload-relative stable path or stable logical name;
- content digest.

Then derive one canonical whole-package fingerprint from that ordered set.

Unknown/missing optional data must remain explicit; do not silently hash an
empty substitute.

---

# D. Requirement 3 — run-specific source provenance

## Problem

Calibration provenance is not the same thing as provenance of the final run.

A run also depends on source that controls:
- mapping;
- code generation;
- build;
- runtime dispatch;
- simulator target construction.

The canonical container may not contain `/workspace/.git`.

## Required change

Introduce run-specific provenance that is clearly distinct from calibration
provenance.

Do not mount `.git` and do not require `.git` to exist in the container.

The new provenance must still be useful when Git metadata is unavailable.

### Required properties

At minimum, run provenance should expose:

```text
K9R5 Git identity when available:
  revision
  dirty
  diff digest
  untracked digest

AND

a deterministic source-set digest for the source files that causally define
the execution path
```

The source-set digest is mandatory even if Git metadata is unavailable.

### Source-set rules

Derive the source set from the actual current execution path. Do not blindly
hash the complete repository.

It should cover the current causal path for heterogeneous execution, including
the relevant source under areas such as:

```text
pipeline/hetero_platform/
pipeline/build_mesh.py
pipeline/run_hetero.py
pipeline/common.py
pipeline/gen_system_header.py

runtime/common/
runtime/mesh/
runtime/snitch/
runtime/spatz/

targets/hetero/
```

For runs launched through the sweep, also include the sweep pieces that
causally construct / calibrate / resolve the design, where appropriate:

```text
pipeline/sweep/design.py
pipeline/sweep/calibrate.py
pipeline/sweep/run.py
```

Use source extensions actually consumed by the project. Keep paths canonical
and repo-relative in the fingerprint input.

Do not include:
- `results/`;
- `work/`;
- `.git/`;
- docs;
- caches;
- temporary files.

If a source set is represented as a list, sort it deterministically.

### Dependencies

Preserve the useful dependency/toolchain/simulator identity already captured by
the current provenance/calibration code.

Avoid duplicating two divergent implementations of the same dependency
fingerprinting logic. Reuse a small helper if that is the least invasive change.

### Manifest

Write run provenance into the run manifest under a clearly named run-specific
location.

Do not label calibration provenance as run provenance.

A reader must be able to distinguish:

```text
calibration identity/provenance
run source identity/provenance
```

---

# E. Requirement 4 — centralize Python implementation/fallback rules

## Problem

The current source-audited MatMul/Gemm fallback truth is operationally in C but
described separately in Python.

Current audited behavior:

### Snitch FP32 MatMul/Gemm

```text
M == 0 or N == 0 -> Generic fallback
O < 8            -> Generic fallback
O % 8 != 0       -> tuned SSR/FREP plus scalar tail
otherwise        -> tuned SSR/FREP
```

### Spatz FP32 MatMul/Gemm

```text
empty dimension             -> Generic fallback
Gemm transA != 0            -> Generic fallback
Gemm transB != 0            -> Generic fallback
otherwise                   -> tuned RVV
```

The same interpretation is currently duplicated between mapper-side safety and
post-run actual-implementation evidence.

## Required change

Create one small pure-Python source of truth for the **Python interpretation**
of the current audited dispatch rules.

Prefer a normalized primitive interface such as:

```python
resolve_matmul_gemm_implementation(
    engine,
    op,
    M,
    N,
    O,
    transA=0,
    transB=0,
)
```

or an equivalent representation.

It should return explicit structured state such as:
- implementation ID when safely known;
- fallback used;
- fallback target;
- fallback reason;
- or explicit unknown when the required facts are unavailable.

Then make both:
- mapper fallback-aware costing;
- `actual_implementation.py`;

consume that shared rule instead of re-implementing it independently.

Do not make this function depend on `onnx_graphsurgeon` if a primitive-data
interface avoids that coupling.

Do not claim this Python function is the operational source of truth. The C
kernel/dispatch remains operational; this is the single audited Python mirror.

## Out of scope

Do NOT:
- modify the C kernels;
- modify mailbox layout;
- add a new runtime beacon;
- add implementation self-reporting to the runtime;
- add timing instrumentation;
- change offload behavior.

Those would make this a different milestone.

---

# F. Execution must not change

This is a critical invariant.

The task must not change:
- selected engine for any fully known current baseline case, except where a
  pre-existing unsafe/unknown path is already intentionally unavailable in M6;
- kernel implementation;
- C kernel code;
- runtime mailbox behavior;
- simulator topology;
- architectural knob defaults;
- calibrated cost formula;
- cycle-counting instrumentation;
- generated network semantics.

There must be no new code in the measured hot path.

Post-run metadata work is allowed.

If a proposed solution requires changing runtime execution, stop and report it
instead of implementing it.

---

# G. Tests

Add focused tests for every new contract.

At minimum cover:

## Manifest

1. new manifest contains all four sections:
   ```text
   request
   resolved
   actual
   measured
   ```
2. measured cycles/correctness are not semantically hidden inside actual state;
3. serialization/fingerprint remains deterministic;
4. compatibility behavior, if any, cannot drift from canonical measured data.

## Workload fingerprint

5. changing `network.onnx` changes whole-workload fingerprint;
6. changing `inputs.npz` changes it;
7. changing `outputs.npz` changes it;
8. changing an application evaluation artifact that is actually consumed
   changes it;
9. changing an unrelated file in the workload directory does NOT change it;
10. artifact order and absolute checkout location do not change it.

## Run provenance

11. changing a selected causal run source changes the run source-set digest;
12. changing an unrelated README/doc does NOT change it;
13. digest is stable across two checkout root locations;
14. Git metadata unavailable remains explicit, while source-set identity still
    exists;
15. calibration provenance and run provenance remain distinguishable.

## Shared implementation rules

16. Snitch O<8 -> Generic fallback;
17. Snitch O==8 -> tuned;
18. Snitch O not divisible by 8 but >=8 -> tuned scalar-tail case;
19. Spatz transposed Gemm -> Generic fallback;
20. Spatz ordinary MatMul/Gemm -> tuned;
21. missing/ambiguous dimensions -> explicit unknown where appropriate;
22. mapper and actual-implementation code consume the same shared rule.

Run the full existing suite after focused tests.

Current pre-M9 gate is:

```text
98 tests passed, 3 subtests passed
```

The final suite should have no regression.

---

# H. Regression / canonical-container validation

If Docker is available to Codex, after all tests pass run a minimal canonical
regression.

At minimum:

### Spatz pinned baseline

```bash
.venv/bin/python pipeline/run_hetero.py \
  ops/mymatmul \
  --host cva6 \
  --pin spatz \
  --timeout 3600 \
  --stall-timeout 180
```

Known frozen reference:

```text
MatMul node cycles = 6694
total cycles       = 8183
status             = ok
maxdiff            = 0.0
```

Do not update the reference if the run changes. Investigate the regression.

If Docker is unavailable, do not alter system permissions. Return one concise
manual validation command for the user.

Do not run Phase B sweeps.

---

# I. Scientific terminology

Use these meanings consistently.

### Node cycles

For current `run_hetero.py` progress instrumentation, node cycles are
host-observed end-to-end node latency around the generated node execution.

For a cluster offload they can include:
- dispatch;
- staging;
- cluster execution;
- stage-out;
- synchronization / wait.

Do not relabel them as pure kernel cycles.

### Total cycles

`host_main.c` measures around `RunNetwork()`, so total cycles can include
progress instrumentation executed inside the network call.

Do not infer:

```text
total cycles - sum(node cycles)
```

as pure architectural overhead.

### Calibration cycles

`mesh_calib.c` provides a distinct engine-side `cycles` and host-observed
`host_cycles`. Preserve that distinction.

---

# J. Documentation cleanup allowed in this milestone

You may make small, source-proved documentation/comment corrections that are
directly relevant to this hardening.

In particular, current stale comments have been observed around the Spatz
cluster shape. If source confirms it, correct comments that still describe the
current baseline Spatz cluster as only two cores / one compute core plus DMA.

Do not broaden this into a documentation rewrite.

Do not change operational code just to make an old comment true.

---

# K. Explicit exclusions

Do NOT implement or begin:

```text
PE/core scaling experiments
lane scaling experiments
PE × lanes experiments
shape sweeps
TCDM sweeps
new mapper strategies
new kernels
tiling
double buffering
precision/quantization
bank-count parameterization
Spatz v3 migration
new accelerator engines
runtime implementation beacons
generic plugin architecture
analysis/plotting framework
```

Do not modify the architectural defaults.

---

# L. Public-repository hygiene

Before finishing:

- run `git diff --check`;
- inspect `git status --short`;
- list all files changed by M9;
- ensure no generated result files were staged/modified by the task;
- ensure no absolute local machine paths enter committed source;
- ensure no credentials/secrets;
- ensure no temp/debug artifacts;
- do not touch the user's known local artifacts unnecessarily.

Do NOT use:

```bash
git add .
git add -A
git clean
git reset --hard
git checkout -- .
```

Do not commit.

Do not push.

---

# M. Final report

Return a concise but complete report containing:

1. audit findings before editing;
2. exact files modified/added;
3. manifest schema change;
4. workload identity design;
5. run provenance design and exact source-set policy;
6. how calibration provenance remains distinct;
7. shared implementation/fallback rule design;
8. focused test results;
9. full test-suite result;
10. canonical Spatz baseline result, if Docker was available;
11. any dependency-blocked validation;
12. `git diff --check` result;
13. `git status --short`;
14. remaining limitations;
15. explicit statement that no Phase B experiment was started;
16. explicit statement that no commit/push/PR/remote mutation occurred.

# N. Acceptance criteria

M9 is acceptable only if all are true:

```text
[ ] request/resolved/actual/measured are first-class manifest concepts
[ ] existing result.json execution format is not broken unnecessarily
[ ] ONNX digest remains identifiable as ONNX digest
[ ] whole workload package gets a separate deterministic fingerprint
[ ] unrelated workload-directory files do not perturb that fingerprint
[ ] run source provenance exists even without .git
[ ] calibration provenance is not mislabeled as run provenance
[ ] mapper and actual implementation share one Python fallback rule
[ ] no runtime/C kernel/mailbox timing path is changed
[ ] full Python test suite passes
[ ] baseline cycles remain unchanged if canonical Docker validation is available
[ ] no Phase B work was started
[ ] no commit/push/PR happened
```

If any acceptance criterion cannot be satisfied without changing runtime
execution or expanding scope, stop and report the blocker rather than widening
the task.
