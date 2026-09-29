# Experimental foundation checkpoints

This document is the **construction history** of the frozen K9R5 experimental
foundation. It answers "how did the implementation get here?" through logical
M1–M9 checkpoints.

For the conceptual overview — what the workbench is, why it exists, how a
researcher uses it, and how discovery/extensibility/auditability fit together —
start with [`../experimental-workbench.md`](../experimental-workbench.md).

## 1. Git lineage

```text
luish18/K9R5
6d40999f244c038f882c5746381f35d565432dcc
        |
        v
45bbb7da05b1df139f03ebf098ffcc2d751262ee
Freeze experimental foundation M1-M8
        |
        v
e97b2dced29352a519d320aeb0b8f871580a589e
Complete experimental provenance foundation M9
```

`45bbb7d` and `e97b2dc` are two commits on `lucas-ic` above the frozen upstream
base. Milestones 1–8 were developed as logical checkpoints in one working-tree
series and committed together at `45bbb7d`; Git therefore does not provide
independent commit boundaries for each M1–M8 step. The milestone mapping below
uses the development records and cross-checks claims against the frozen source.

Some experiment/fingerprint/provenance primitives were already present in the
working tree when the numbered milestones began, even though they are part of
the overall `6d40999..45bbb7d` branch delta. They are documented as foundation
components rather than retroactively assigned to a milestone that did not
create them.

## 2. What already existed at the upstream base

The upstream base is a substantial system, not an empty scaffold. At
`6d40999`, K9R5 already contains the principal heterogeneous execution stack,
including:

- CVA6 host and heterogeneous Snitch/Spatz target construction;
- Deeploy-based ONNX generation and heterogeneous platform integration;
- host/cluster runtime, mailbox/offload path and TCDM staging;
- tuned Snitch FP32 MatMul/Gemm based on SSR/FREP;
- tuned Spatz FP32 MatMul/Gemm based on RVV;
- Generic fallbacks and symbol-override build machinery;
- cost-based heterogeneous mapper;
- design-space sweep and per-design calibration machinery;
- MNIST and KWS application paths;
- simulator/memory instrumentation, Docker workflow and GUI support.

In particular, these source files already exist at the upstream checkpoint:

```text
runtime/snitch/kernels/gemm_fp32_ssr.c
runtime/spatz/kernels/gemm_fp32_rvv.c
pipeline/hetero_platform/mapper.py
pipeline/sweep/run.py
```

The foundation therefore organizes, describes, audits and hardens those
mechanisms; it does not claim authorship of them.

## 3. What the foundation adds conceptually

The branch delta introduces an experiment-facing layer around the operational
stack. Its contribution is easier to understand in three groups than as nine
independent features:

```text
INTERFACE / DISCOVERY
- ExperimentRequest
- deterministic resolution
- parameter/engine/host/mapping/kernel catalogs
- workload inspection
- gui_query discovery surface

AUDITABILITY / EXTENSION STRUCTURE
- ResolvedExperiment
- ResourceSummary
- implementation/fallback identity
- mapping explanation
- workload/calibration/run fingerprints and provenance
- extension-seam documentation/invariants

SCIENTIFIC SAFETY / HARDENING
- unknown remains unknown
- missing cost/rate data is not silently borrowed or fabricated
- deterministic Generic fallback is not priced as tuned execution
- calibration/run artifacts carry stronger identity
- stale/mismatched harness state is detected or refreshed
```

The M1–M9 sections below record **how those capabilities were built and
validated**.

## 4. Logical milestones

### M1 — Current state and sweep pin

**Objective.** Verify the workbench state and make the existing
`run_hetero.py --pin` mechanism usable from controlled sweeps without changing
its semantics.

**Principal surfaces.**

- `pipeline/sweep/run.py`
- `pipeline/experiment/schema.py`
- `pipeline/experiment/resolve.py`
- sweep/pin tests and manifest metadata

**Result.**

A sweep can request `--pin cva6|snitch|spatz`; the value propagates through the
request/resolved metadata and to `run_hetero.py`.

**Semantic constraint.**

Pinning is compatible-node selection, not whole-graph execution. Unsupported
nodes may remain on other engines.

**Robustness value.**

Mapped-vs-pinned comparisons can be represented in experiment identity instead
of being inferred from a shell command.

**Validation record.**

The next milestone's development record states that M1 closed with 60/60
canonical Python tests and a real pinned-Spatz sanity run in which the MatMul
executed on Spatz and the pin was preserved in metadata.

**Execution effect.**

No-pin behavior is preserved. A requested pin intentionally changes placement
for compatible nodes by using the pre-existing pin mechanism.

### M2 — ResourceSummary

**Objective.** Stop shorthand such as "9 cores vs 9 cores" from silently
implying equal compute resources.

**Principal surfaces.**

- `pipeline/experiment/resource_summary.py`
- resolved-experiment schema/serialization
- `targets/hetero/system.py` invariants
- `pipeline/tests/test_resource_summary.py`

**Result.**

A resolved design exposes descriptive resources such as modeled cores, compute
cores, control/DMA cores, TCDM organization, and Spatz modeled/useful vector
lanes.

For the current runtime convention:

```text
compute cores = modeled cluster cores - 1 control/DMA core
```

Spatz reports modeled and useful vector lanes so the VPU attached to the
control/DMA core is not silently counted as useful compute.

**Limitations.**

The summary does not infer area, power or architectural equivalence.

**Execution effect.**

None. `ResourceSummary` is derived metadata.

### M3 — KernelImplementation catalog

**Objective.** Give stable identities to concrete implementation paths that
already exist and document how build/runtime reaches them.

**Principal surfaces.**

- `pipeline/experiment/kernel_implementation_catalog.py`
- discovery/query integration
- catalog drift tests

**Stable current FP32 MatMul/Gemm identities.**

```text
cva6.fp32.matmul_gemm.deeploy_generic
snitch.fp32.matmul_gemm.ssr_frep
snitch.fp32.matmul_gemm.deeploy_generic_fallback
spatz.fp32.matmul_gemm.rvv_tuned
spatz.fp32.matmul_gemm.deeploy_generic_fallback
```

The catalog checks source/symbol/build-dispatch assumptions instead of becoming
a new selector.

**Execution effect.**

None. The catalog shadows existing behavior.

### M4 — Actual implementation and fallback evidence

**Objective.** Connect completed runtime nodes to the implementation path that
handled them, without guessing from mapper placement alone.

**Principal surfaces.**

- `pipeline/experiment/actual_implementation.py`
- generated kernel-argument metadata
- heterogeneous run post-processing
- actual-implementation tests

**Result.**

Completed MatMul/Gemm nodes can carry:

- implementation ID;
- fallback used/unknown;
- fallback source/target;
- fallback reason;
- implementation detail;
- evidence type.

Evidence is deterministic from a completed runtime beacon, matching generated
node metadata, required kernel arguments and compiled dispatch. Missing or
contradictory evidence remains unknown.

**Measurement effect.**

This is post-simulation metadata and does not add hot-path logging solely to
identify the implementation.

### M5 — Mapping explainability

**Objective.** Explain the current mapper decision without changing mapping
policy.

**Principal surfaces.**

- `pipeline/hetero_platform/mapper.py`
- `pipeline/experiment/mapping_strategy_catalog.py`
- generated mapping serialization
- mapping-explanation tests

**Result.**

Per-node metadata can expose:

- strategy identity;
- compatible/incompatible engines;
- pin filtering;
- cost availability;
- rate and rate provenance;
- offload/staging terms;
- final estimated cost;
- selected engine and selection rule.

This exposed unsafe behavior that was then hardened in M6.

**Execution effect.**

Descriptive by design; the milestone preserves selection semantics.

### M6 — Safety hardening

**Objective.** Eliminate concrete silent ambiguities found by the audits.

**Principal surfaces.**

- `pipeline/hetero_platform/engines.py`
- `pipeline/hetero_platform/mapper.py`
- workload/mapper safety tests
- implementation/fallback rules

**Hardened behavior.**

1. unknown tensor size is not zero;
2. incomplete MAC estimates do not become fabricated costs;
3. unknown engine rates do not borrow CVA6 rates;
4. missing/invalid rate or cluster-overhead data remains explicit;
5. `_default` is labelled as proxy, not operator measurement;
6. external calibration tables replace rather than merge active tables;
7. deterministic tuned-to-Generic fallback is not priced with a tuned rate;
8. Snitch scalar tail remains a tuned case, not whole-kernel fallback;
9. pin semantics remain compatible-node pinning.

**Execution effect.**

Automatic mapping may change only in cases that were previously unsafe or
ambiguous. Safely priced valid mappings are intended to retain their previous
selection.

### M7 — Extension-seam audit

**Objective.** Make expected research extensions explicit without building a
generic plugin framework.

**Principal surface.**

- `docs/dev/extension-seams.md`
- catalog/resolver/drift invariants and focused tests

**Result.**

The audit identifies entry points, identities, propagation paths, tests and
limitations for:

- workloads;
- hardware knobs;
- kernel implementations;
- mapping strategies;
- simulator/host profiles;
- future precision;
- future engines.

The frozen classifications are intentionally conservative: workloads, hardware
knobs and kernel implementations are `ready with local change`; mapping
strategies, simulator/host profiles and future engines are `fragile`; precision
is `blocked`.

The point is not that future features become trivial. The point is that their
experiment-facing consequences no longer need a new identity/provenance/
manifest/discovery design each time.

**Execution effect.**

No new research feature is introduced by the audit itself.

### M8 — Full validation and foundation freeze

**Objective.** Validate the M1–M7 contract and repair only defects that would
invalidate the freeze.

**Validation classes.**

- unit/pure Python;
- structural/serialization;
- golden/regression;
- adversarial/safety;
- canonical-container integration;
- scientific invariants.

**Two concrete harness defects found during the freeze audit.**

1. **Ara calibration host mismatch.** A sweep could select Ara for the final
   simulator run while calibration build still used the scalar CVA6 host image.
   The frozen path propagates the selected host into the calibration build.
2. **Stale per-design mesh copy.** Reusing a sweep output directory after
   runtime changes could compile a stale per-design `runtime/mesh` copy. The
   frozen path refreshes that copy before regenerating system headers.

These are operational harness fixes, not new architecture features.

**Freeze.**

```text
45bbb7da05b1df139f03ebf098ffcc2d751262ee
Freeze experimental foundation M1-M8
```

### M9 — Run identity and provenance hardening

**Objective.** Close remaining identity/provenance gaps without changing
simulated execution.

**Principal surfaces.**

- `pipeline/experiment/run_manifest.py`
- `pipeline/experiment/provenance.py`
- `pipeline/experiment/workload.py`
- `pipeline/experiment/matmul_gemm_implementation.py`
- `pipeline/experiment/actual_implementation.py`
- mapper/sweep integration and focused tests

**Changes.**

1. manifest schema v2 separates first-class `actual` from canonical `measured`;
2. workloads receive a whole-package fingerprint in addition to ONNX digest;
3. final runs receive source provenance separate from calibration provenance;
4. Snitch/Spatz MatMul/Gemm fallback interpretation is centralized in one
   audited Python mirror while C remains operational truth;
5. deterministic causal source-set digest participates in `run_fingerprint`;
6. one stale Spatz cluster-count comment was corrected to the current nine
   modeled cores; operational count remains sourced from target/system code.

**Regression tests added in the final follow-up.**

- changing selected `pipeline/run_hetero.py` changes `run_fingerprint`;
- changing an unrelated README does not.

**Final canonical validation.**

```text
Python suite: 106 tests passed

Pinned Spatz, ops/mymatmul 32x32x32:
  status       ok
  node cycles  6694
  total cycles 8183
  maxdiff      0.0
```

The frozen values remained unchanged, supporting the claim that M9 hardened
identity/provenance rather than changing simulated execution.

**Freeze.**

```text
e97b2dced29352a519d320aeb0b8f871580a589e
Complete experimental provenance foundation M9
```

## 5. Important implementation facts preserved by the audit

### Snitch MatMul/Gemm

```text
M == 0 or N == 0 -> Deeploy Generic whole-kernel fallback
O < 8            -> Deeploy Generic whole-kernel fallback
O >= 8           -> tuned SSR/FREP
O >= 8, O % 8    -> tuned SSR/FREP plus internal scalar tail
```

### Spatz MatMul/Gemm

```text
any empty dimension        -> Deeploy Generic whole-kernel fallback
Gemm transA != 0           -> Deeploy Generic whole-kernel fallback
Gemm transB != 0           -> Deeploy Generic whole-kernel fallback
otherwise                  -> tuned RVV
```

### Resource interpretation

At the baseline design each cluster has nine modeled cores. The runtime
convention reserves one control/DMA core, leaving eight compute cores. With
four Spatz lanes per modeled VPU core, `ResourceSummary` distinguishes 36
modeled lanes from 32 useful lanes.

These are modeled-resource descriptions, not area/power equivalence claims.

## 6. Things deliberately not claimed by this foundation

The foundation does **not** claim:

- authorship of K9R5 or its original heterogeneous SoC/runtime;
- authorship of tuned Snitch/Spatz kernels already present at `6d40999`;
- that a mapper estimate is actual execution evidence;
- that a pin is whole-graph isolation;
- that host-observed node latency is pure kernel-body cycles;
- that equal modeled cores, compute cores or useful vector lanes imply equal
  area or power;
- that every exposed hardware knob is already causally validated;
- that the current mapper is globally optimal;
- that one architecture is generally superior to another.

## 7. What the freeze enables next

The next sequence is:

```text
causal knob audit
        ->
reference validation (Snitch / Spatz / Deeploy)
        ->
small pilot
        ->
controlled architectural campaigns
```

See [`../experimental-workbench.md`](../experimental-workbench.md) for the
research workflow and [`k9r5-workbench-roadmap.md`](k9r5-workbench-roadmap.md)
for later directions.
