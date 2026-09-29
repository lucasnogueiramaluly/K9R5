# K9R5 experimental workbench

This is the primary researcher-facing overview of the experiment layer frozen
on branch `lucas-ic` at:

```text
e97b2dced29352a519d320aeb0b8f871580a589e
Complete experimental provenance foundation M9
```

Its frozen upstream reference point is `luish18/K9R5` at
`6d40999f244c038f882c5746381f35d565432dcc`. The intermediate checkpoint
`45bbb7da05b1df139f03ebf098ffcc2d751262ee` freezes logical Milestones 1–8.

This document explains **what the workbench layer is, why it exists, how a
researcher uses it, and which guarantees it provides**. The chronological
M1–M9 construction history lives in
[`dev/foundation-checkpoints.md`](dev/foundation-checkpoints.md). Future work
lives in [`dev/k9r5-workbench-roadmap.md`](dev/k9r5-workbench-roadmap.md).

The layer documented here does **not** claim to have created K9R5, the
heterogeneous CVA6/Snitch/Spatz SoC, Deeploy integration, the host/cluster
runtime, the existing tuned Snitch SSR/FREP or Spatz RVV kernels, the original
mapper/sweep/calibration machinery, or the MNIST/KWS applications. Those paths
already exist at the frozen upstream base. The `lucas-ic` work organizes an
experiment-facing interface around that stack and hardens it for controlled
research.

## 1. From K9R5 platform to experimental workbench

The upstream K9R5 was already a substantial experimental platform. It could
build and simulate a heterogeneous SoC, generate code from ONNX through
Deeploy, offload work to Snitch and Spatz clusters, calibrate the mapper, run
sweeps, execute application workloads, and report performance data.

The structural audit did not conclude that this stack should be replaced by a
new framework. Instead, it identified a different problem: **a researcher had
to know too much of the repository's internal coupling to discover, describe,
extend, and later reconstruct an experiment**.

Important facts existed, but were spread across operational layers:

- design defaults and validation;
- target/simulator construction;
- engine names and capabilities;
- build and runtime dispatch;
- kernel implementations and fallback conditions;
- mapper cost inputs;
- workload/application metadata;
- GUI/CLI choices;
- calibration and result artifacts.

Some of this duplication was only descriptive metadata and was worth
centralizing. Other parts carry real operational semantics and deliberately
remain specific: operand staging, scratch planning, multicore partitioning,
kernel bodies, GVSoC retune adapters, and application-specific runtime logic
are not turned into generic configuration merely for uniformity.

### Before and after

| Research question | Before the foundation | With the frozen workbench |
|---|---|---|
| What knobs exist? | Inspect design code/documentation and understand local rules | parameter catalog + `gui_query.py knobs` |
| How do I request an experiment? | Compose driver/sweep flags and know implicit defaults | small `ExperimentRequest` |
| What complete configuration does that mean? | Reconstruct defaults and derived state from several modules/artifacts | deterministic `ResolvedExperiment` |
| What resources does the design represent? | Interpret core/lane/TCDM conventions manually | derived `ResourceSummary` |
| What kernel implementations exist? | Trace source, build overrides and runtime dispatch | `KernelImplementation` catalog |
| Which implementation handled this completed node? | Infer it from engine/build/arguments | explicit implementation/fallback evidence where source-grounded |
| Why did the mapper choose an engine? | Read mapper code and calibration tables | per-node mapping explanation |
| Is cached calibration still valid? | Trust the artifact path/convention | calibration identity, metadata and staleness checks |
| How does a tool/GUI discover current choices? | Mix Python queries with local hard-coded choices | common query/discovery surface derived from Python sources |
| How do I reproduce a run? | Collect configuration, artifacts and source context manually | request/resolved/actual/measured + fingerprints/provenance |
| Where does a future extension enter? | Rediscover coupled integration points | documented extension seams and protecting invariants |

The goal is **not** to make every extension a one-line plugin. A new engine, for
example, still requires real target, build, runtime, Deeploy, kernel and
calibration work. The workbench makes the experiment-facing consequences
explicit so that identity, discovery, provenance, validation and manifests do
not have to be reinvented for each extension.

### Three responsibilities of the foundation

The resulting layer has three complementary responsibilities:

```text
1. RESEARCHER INTERFACE / DISCOVERY
   minimal request
   deterministic resolution
   catalogs and query API

2. AUDITABILITY / EXTENSION STRUCTURE
   explicit resources
   kernel identity
   mapping explanation
   fingerprints and provenance
   documented extension seams

3. SCIENTIFIC SAFETY / HARDENING
   unknown stays unknown
   missing cost is not fabricated
   tuned estimate is not Generic fallback execution
   stale/mismatched artifacts are rejected or exposed
```

M1–M9 are the implementation history of those responsibilities, not the
conceptual definition of the workbench.

## 2. Researcher-facing interface

A researcher should specify the decisions they want to make, not manually fill
a manifest.

For example, the experiment-facing request can be as small as:

```json
{
  "platform": "k9r5_current",
  "workload": "ops/mymatmul",
  "design_overrides": {
    "SPATZ_NB_LANES": 8
  },
  "pin": "spatz"
}
```

The resolver then derives the complete state:

```text
ExperimentRequest
        |
        v
resolve_experiment()
        |
        +-- complete hardware design + fingerprint
        +-- ResourceSummary
        +-- host/simulator profile
        +-- workload identity/descriptors
        +-- mapping strategy + pin semantics
        +-- execution flags
        |
        v
ResolvedExperiment
```

Defaults and derived facts therefore do not have to be duplicated in every
request. Unknown request fields, unknown knobs, unknown engine IDs and invalid
designs are rejected explicitly.

### Discovery and query surface

`pipeline/gui_query.py` is the thin JSON query bridge used by front-ends so
that tools do not have to reproduce Python rules:

```bash
.venv/bin/python pipeline/gui_query.py env
.venv/bin/python pipeline/gui_query.py ops
.venv/bin/python pipeline/gui_query.py knobs
.venv/bin/python pipeline/gui_query.py experiment-schema
.venv/bin/python pipeline/gui_query.py inspect ops/mymatmul
```

A complete request can be resolved without building or simulating:

```bash
cat >/tmp/k9r5-request.json <<'EOF'
{
  "platform": "k9r5_current",
  "workload": "ops/mymatmul",
  "design_overrides": {},
  "host": "cva6",
  "mapping_strategy": "measured_rate_greedy",
  "pin": "spatz"
}
EOF

.venv/bin/python pipeline/gui_query.py resolve-experiment \
  /tmp/k9r5-request.json | .venv/bin/python -m json.tool
```

This interface is useful to a CLI, GUI, automation, or future agent because it
asks the audited Python sources what exists instead of copying independent
choice lists.

## 3. Experimental contract

The workbench keeps four layers distinct:

```text
REQUESTED
what the researcher explicitly asked for
        |
        v
RESOLVED
the complete deterministic configuration implied by that request
        |
        v
ACTUAL
what mapping/configuration facts were used for this run
        |
        v
MEASURED
cycles, correctness, accuracy, counters and other observations
```

### Requested

`ExperimentRequest` currently records experiment-facing choices including:

- platform (`k9r5_current`);
- workload;
- design overrides;
- host profile (`cva6` or `ara`);
- mapping strategy;
- optional compatible-node pin;
- KWS front-end/serial choices;
- power measurement request.

The request is intentionally incomplete.

### Resolved

`ResolvedExperiment` expands a request into a deterministic description
containing:

- full resolved design and hardware fingerprint;
- `ResourceSummary`;
- host profile and simulator target;
- workload metadata and workload fingerprint;
- mapping strategy identity and pin semantics;
- execution flags.

### Actual

Run-manifest schema v2 stores `actual` separately from measurements. In the
current sweep integration, `actual.mapping` is the generated mapping document,
including node placement and mapping explanation.

Post-simulation implementation evidence is joined to completed runtime node
beacons and is currently stored with the corresponding measured node record
(`measured.nodes[].implementation`). Conceptually that evidence describes what
executed; its storage location follows the existing result structure and must
not be confused with a mapper prediction.

### Measured

`measured` is the canonical observation object in manifest schema v2. It
contains the result produced by `run_hetero.py`, including fields such as:

- run status;
- total cycles;
- per-node/per-engine cycles;
- correctness and numerical error;
- application accuracy/agreement where applicable;
- offload failures;
- cache counters;
- wall time;
- completed node implementation evidence.

Legacy callers that pass observations through `actual.result` are normalized
in memory; new manifests do not persist two independent copies.

## 4. Catalogs, resources and operational truth

The experiment layer adds **descriptive** catalogs. It does not move simulator
or runtime behavior into a second configuration system.

| Surface | Purpose | Operational truth remains in |
|---|---|---|
| parameter catalog | names, units and descriptions for supported design knobs | `pipeline/sweep/design.py` and target consumers |
| engine catalog | stable logical engine metadata | heterogeneous target/runtime engine IDs |
| host profile catalog | scalar CVA6 vs CVA6+Ara experiment-facing profiles | `pipeline/build_mesh.py::HOSTS` |
| mapping strategy catalog | stable identity for current mapper behavior | `pipeline/hetero_platform/mapper.py` |
| kernel implementation catalog | source/build/dispatch inventory for audited FP32 MatMul/Gemm paths | build/runtime/kernel sources |
| workload inspection | ONNX structure, descriptors and package identity | actual workload package |
| `ResourceSummary` | derived modeled/useful resources for a resolved design | resolved design + target/runtime invariants |

`ResourceSummary` is particularly important for comparisons. A baseline Snitch
and Spatz cluster can both have nine modeled cores and eight compute cores
without being resource-equivalent. With four Spatz lanes per modeled VPU core,
the baseline summary distinguishes 36 modeled lanes from 32 useful lanes on
compute cores.

Those are **modeled resource counts**. They do not imply equal area, equal
power, or equal effective compute capability.

## 5. Extensibility without hiding operational semantics

The foundation does not implement every future feature. It establishes explicit
places where those features must enter and which existing invariants must
continue to hold.

The detailed source-grounded guide is
[`dev/extension-seams.md`](dev/extension-seams.md). Its frozen classifications
are:

| Extension | Current seam |
|---|---|
| workload/model | ready with local change |
| hardware/design knob | ready with local change |
| kernel implementation | ready with local change |
| mapping strategy | fragile |
| simulator/host profile | fragile |
| precision | blocked |
| future engine | fragile |

The classifications are intentionally conservative. A catalog row is not
support. A knob name is not causal validation. A new engine is not integrated
because its ID appears in discovery.

Examples of the intended extension discipline:

- **new workload**: reuse workload inspection, package identity, resolver,
  manifests and sweep integration; add application-specific generation only
  where the workload actually needs it;
- **new supported hardware knob**: add resolved design/default/validation,
  target propagation, descriptive metadata and resource/calibration effects
  where applicable;
- **new kernel implementation**: implement source/build/runtime behavior first,
  then assign stable catalog/evidence identity;
- **new mapper strategy**: first bind strategy identity to a real operational
  factory; descriptive metadata alone is insufficient;
- **new precision**: must propagate through request, tensor bytes, capability,
  calibration, cost identity, actual implementation and measured correctness;
- **new engine**: still requires an end-to-end hardware/software integration,
  but should reuse the existing experiment identity, discovery, provenance and
  manifest contracts.

This is deliberately different from a generic plugin framework. The foundation
centralizes repeated **identity and metadata** while preserving specific
operational semantics where genericization would hide real behavior.

## 6. Identity and provenance

### 6.1 Design identity

A resolved design contains all supported design values, a stable design slug,
a build key and a fingerprint of the resolved hardware dictionary. A partial
request and the complete resolved configuration therefore remain
distinguishable.

`ResourceSummary` derives descriptive resources from the resolved design rather
than becoming another source of configuration truth.

### 6.2 Workload identity

`WorkloadSpec.content_digest` remains the ONNX model entrypoint digest.

`WorkloadSpec.workload_fingerprint` is a separate whole-package identity over
selected workload artifacts currently consumed by the path:

- ONNX model;
- `inputs.npz`, when present;
- `outputs.npz`, when present;
- detected application data header, when present and consumed.

Each selected file appears in `artifact_digests`. Unrelated README files, logs,
results and generated work directories are excluded.

### 6.3 Calibration identity and provenance

Sweep calibration is per resolved design. `calibration.json` records an input
fingerprint over the calibration protocol, host, resolved design, selected K9R5
calibration sources, dependency identities, local GVSoC patches, toolchain
identity and simulator binary digest.

The sidecar is checked before cached rates are reused. A `rates.json` file is
not accepted merely because its path exists.

Calibration provenance and final-run provenance are intentionally distinct.

### 6.4 Run source provenance

`run_provenance` records:

- optional K9R5 Git identity when `.git` is available;
- mandatory deterministic digest of the selected causal source set;
- selected source paths;
- whether sweep-specific sources were included.

The source set covers the current heterogeneous pipeline/runtime/target path and
excludes documentation, results and generated output.

The run fingerprint includes the deterministic
`run_provenance.source_set.digest`; it does not directly hash the optional Git
snapshot. This keeps source identity meaningful in a source-only runtime
container without `.git`.

### 6.5 Run fingerprint

At the frozen M9 checkpoint, `run_fingerprint` derives from:

- request;
- resolved experiment;
- actual mapping;
- measured result;
- calibration input fingerprint;
- calibration metadata digest;
- result artifact digest;
- causal run source-set digest.

A selected causal source change therefore changes run identity even if the
request and observed numbers happen to remain unchanged. A change to an
unrelated README is tested not to change it.

## 7. Mapping safety and explainability

The current strategy identity is `measured_rate_greedy`. For automatic mapping
it compares compatible engines using the existing cost model:

```text
estimated cycles =
    fixed offload
  + per-byte staging cost
  + estimated MACs / measured-or-explicit-proxy rate
```

The foundation exposes the inputs/exclusions and hardens concrete unsafe cases:

- unknown working-set size is not treated as zero;
- incomplete shape-derived MAC count makes cost unavailable;
- missing/unknown engine rate rows do not borrow CVA6 rates;
- missing or invalid operator rates remain unavailable;
- `_default` is explicit proxy data, not an operator measurement;
- external `HES_RATES` tables replace the active tables rather than silently
  merging measurements from two configurations;
- a MatMul/Gemm invocation that deterministically falls back to Generic is not
  priced with a tuned implementation rate;
- if no compatible engine has a safe cost, automatic mapping records that
  condition instead of inventing a value.

Mapping explanations preserve compatibility, pin influence, cost
availability/provenance, selected engine and selection rule.

### Pin semantics

`--pin cva6|snitch|spatz` is a compatible-node preference/constraint, **not** a
whole-graph promise. When the pinned engine can execute the node, it is
selected. Nodes the pinned engine cannot execute may remain elsewhere.

Always inspect actual mapping rather than infer placement from the requested
pin alone.

## 8. MatMul/Gemm implementation and fallback evidence

The tuned kernels predate this foundation. The foundation catalogs their
existing paths and adds source-grounded post-run evidence.

C remains operational truth. The helper
`pipeline/experiment/matmul_gemm_implementation.py` is the single audited
Python interpretation used by mapper safety and post-run evidence; it is not a
dispatcher.

Current audited FP32 rules:

| Engine | Condition | Implementation interpretation |
|---|---|---|
| CVA6 | MatMul/Gemm | Deeploy Generic |
| Snitch | `M == 0` or `N == 0` | whole-kernel Generic fallback |
| Snitch | `O < 8` | whole-kernel Generic fallback |
| Snitch | `O >= 8`, `O % 8 == 0` | tuned SSR/FREP |
| Snitch | `O >= 8`, `O % 8 != 0` | tuned SSR/FREP plus internal scalar tail |
| Spatz | any empty dimension | whole-kernel Generic fallback |
| Spatz Gemm | `transA != 0` or `transB != 0` | whole-kernel Generic fallback |
| Spatz | otherwise | tuned RVV |

The Snitch scalar tail is **not** a whole-kernel fallback.

Implementation evidence becomes known only when completed runtime metadata can
be joined consistently with generated node metadata and required kernel
arguments. Missing arguments, unsupported operators/engines, or disagreement
between generated metadata and runtime evidence remain explicit unknowns.

## 9. Using the workbench

### 9.1 Direct heterogeneous run

Mapped run:

```bash
.venv/bin/python pipeline/run_hetero.py ops/mymatmul
```

Controlled compatible-node pin:

```bash
.venv/bin/python pipeline/run_hetero.py ops/mymatmul \
  --pin spatz \
  --out /tmp/k9r5-spatz-result.json
```

A direct `run_hetero.py` invocation writes the result document. The richer
request/resolved/actual/measured manifest is produced by the sweep path.

### 9.2 Minimal manifest-producing smoke cell

```bash
rm -rf work/experimental-smoke
.venv/bin/python pipeline/sweep/run.py \
  --models ops/mymatmul \
  --pin spatz \
  --limit 1 \
  -o work/experimental-smoke
```

For this workload the relevant artifacts are:

```text
work/experimental-smoke/
├── sweep.jsonl
├── designs/
│   └── baseline/
│       ├── design.json
│       ├── rates.json
│       └── calibration.json
└── cells/
    └── baseline__mymatmul/
        ├── result.json
        └── manifest.json
```

Inspect them with:

```bash
.venv/bin/python -m json.tool \
  work/experimental-smoke/cells/baseline__mymatmul/manifest.json

.venv/bin/python -m json.tool \
  work/experimental-smoke/designs/baseline/calibration.json
```

### 9.3 Small explicit sweep

Only use a knob as a scientific axis after its causal path has been audited.
Once approved:

```bash
.venv/bin/python pipeline/sweep/run.py \
  --models ops/mymatmul \
  --knob SPATZ_NB_LANES=2,4,8 \
  --pin spatz \
  -o work/sweeps/spatz-lanes-pilot
```

The baseline is prepended and duplicate resolved designs are removed.

## 10. Measurement semantics

The frozen pinned-Spatz `ops/mymatmul` 32x32x32 reference produced:

```text
status       ok
node cycles  6694
total cycles 8183
maxdiff      0.0
```

These cycle fields have different scopes.

`node cycles` comes from `hes_node_begin()`/`hes_node_end()` around the
generated node execution block on the host. For an offloaded node this is
**host-observed end-to-end node latency** and can include dispatch, staging,
cluster execution, synchronization and waiting. It is not automatically a
kernel-body cycle count.

`total cycles` is measured around `RunNetwork()` in the host program and also
contains progress instrumentation executed inside that call. Therefore:

```text
total cycles - sum(node cycles)
```

must **not** be labelled "pure architectural overhead" without a more specific
measurement.

For decomposition work, `runtime/tests/mesh_calib.c` separately records
cluster-side job `cycles` and host-observed round-trip `host_cycles`. In the
current cluster runtime, the cluster-side timer starts before argument handling
and operand staging and ends after output stage-out, so it includes staging,
barriers/control and compute; it is **not** a pure kernel-body timer.

Wall-clock simulation time is a host/tool throughput metric, not architectural
latency.

## 11. Reproducible comparison workflow

For a controlled experiment:

1. start from a known repository commit;
2. record the minimal request;
3. resolve it and inspect the complete design/resource description;
4. use the sweep path when the result needs a full manifest;
5. inspect `actual.mapping`; do not infer placement from a requested pin;
6. inspect implementation/fallback evidence where available;
7. check workload fingerprint and selected artifacts;
8. check calibration fingerprint/provenance and reuse status;
9. check run source-set provenance and `run_fingerprint`;
10. verify that the intended controlled difference is the difference represented
    in the manifests;
11. preserve manifest, result and calibration artifacts together.

A comparison is suspect when, for example:

- the requested knob changed but the constructed simulator path has not been
  causally audited;
- workload identity changed unexpectedly;
- calibration belongs to another design/source/toolchain/simulator;
- actual mapping or fallback differs from the intended comparison;
- a conclusion assumes a direct operator measurement but the mapper used an
  explicit proxy;
- source identity changed for reasons outside the research question.

## 12. Validation status at the frozen checkpoint

### Validated now

At `e97b2dc`, final canonical validation recorded:

- 106 Python tests passing in the canonical container;
- pinned Spatz 32x32x32 MatMul preserved exactly:
  `node=6694`, `total=8183`, `status=ok`, `maxdiff=0.0`;
- deterministic manifest serialization;
- selected causal source changes alter `run_fingerprint`;
- unrelated README changes do not alter `run_fingerprint`;
- selected workload artifact changes alter the whole-workload fingerprint;
- unrelated workload documentation is excluded from that fingerprint;
- source-audited implementation/fallback rules have focused regression tests.

This validates the experiment-description/auditability foundation and preserves
the frozen operational regression.

### Not yet causally validated for scientific sweeps

A knob being present in `pipeline/sweep/design.py`, discovery, a resolved
experiment or `ResourceSummary` does **not** prove that changing it changes the
constructed simulator exactly as intended.

For every scientific axis, validate:

```text
request/override
    -> resolved design
    -> HES_DESIGN / target configuration
    -> GVSoC construction
    -> runtime-visible state where applicable
    -> measured behavior
```

Immediate targets include:

- `SNITCH_NB_CORE`;
- `SPATZ_NB_CORE`;
- `SPATZ_NB_LANES`;
- selected TCDM/memory parameters for later studies;
- build-time VLEN parameters if used as study axes.

The metadata layer already tests resolution/resource consistency. The missing
proof is the end-to-end causal simulator/hardware path needed for scientific
interpretation.

## 13. Scientific questions the foundation deliberately does not answer

The foundation makes future experiments safer; it does not itself resolve the
architecture questions.

Open questions include:

- normalized Snitch/Spatz comparisons: same compute-core count, constant useful
  vector-lane count, reference/paper-like configurations, and other controlled
  normalizations;
- fidelity of the specific GVSoC Spatz model relative to upstream/current
  Spatz configurations and published reference points;
- TCDM bank-count effects where a suitable model/knob is available;
- software maturity asymmetry between engines/operators, especially when one
  path has a tuned kernel and another relies on Generic/compiler-generated code;
- tiling, residency, DMA overlap/double buffering;
- future precision/quantization;
- defensible physical area/power comparisons;
- richer mapping/scheduling policies.

The workbench exposes enough identity and resource context to study these
questions without pretending they are already solved.

## 14. Next scientific phase

The sequence after the documentation/foundation freeze is:

```text
1. causal knob audit
        |
        v
2. external/reference validation
   Snitch / Spatz / Deeploy
        |
        v
3. small pilot
   determinism + a few designs/shapes
        |
        v
PHASE B
controlled architectural experiments
```

Phase B then begins narrow and expands only after the mechanism is understood:

```text
Spatz PE/core scaling
        |
        v
Snitch PE/core scaling
        |
        v
Spatz lane scaling
        |
        v
PE x lanes organization
        |
        v
shape/reuse regimes
        |
        v
mapping studies
        |
        v
memory/TCDM sensitivity
        |
        v
application-level studies
```

The objective is not a universal architecture ranking. It is to identify
workload and architectural regimes, understand the mechanism behind the trend,
and preserve enough evidence to reproduce the conclusion.

## 15. Deliberate non-claims

The frozen foundation does not establish:

- authorship of K9R5 or the underlying heterogeneous SoC/runtime;
- authorship of tuned Snitch/Spatz kernels that predate the branch;
- that equal core counts imply equal compute, area or power;
- that equal useful vector-lane counts imply equal area or power;
- that node cycles or calibration cluster-side cycles are pure kernel-body
  cycles;
- that every exposed knob is already causally validated;
- that the current mapper is globally optimal;
- that one engine is generally superior to another;
- that the current GVSoC model is equivalent to RTL synthesis or silicon
  measurements.

Those claims require separate evidence.
