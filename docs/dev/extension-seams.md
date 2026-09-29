# K9R5 extension seams

This note identifies the current, source-grounded places where an extension
enters K9R5.  It is an implementation guide, not a second configuration
system.  Operational sources remain authoritative.

## Classification

- **ready**: a new instance has a local, explicit path and existing checks.
- **ready with local change**: the path is local, but one or a few identified
  implementation sites must be extended.
- **fragile**: the path crosses manually coupled operational sites; establish
  the missing binding before treating the extension as a routine variant.
- **blocked**: the current system has no defensible implementation path.

## Workload or model — ready with local change

The experiment-facing entry is an ONNX file or an operation directory holding
`network.onnx`; `pipeline/experiment/workload.py::inspect_workload` resolves
the static `WorkloadSpec`, content digest, tensor descriptors, and known versus
unknown shape facts.  `pipeline/gui_query.py` exposes inspection and resolution;
`pipeline/sweep/run.py::run_cell` resolves the same workload before writing the
run manifest.

To add a workload, create/export the ONNX model and its test inputs/outputs in
the existing operation layout.  Add application generation only when it is an
application workload, then verify the path through `resolve_workload_path`,
`detect_app`, code generation, and the resulting manifest.  A new ONNX
operator also requires a real Deeploy mapping/kernel path before it can run;
the workload descriptor alone is not a support claim.

Identity and provenance are the requested path, resolved `WorkloadSpec.path`,
and `WorkloadSpec.content_digest`; the resolved experiment and run manifest
retain them.  `test_workload_spec.py`, `test_resolve.py`, and manifest tests
protect static inspection, unknown-shape handling, deterministic resolution,
and serialization.  The limitation is that discovery is path-based rather than
a workload catalog, deliberately avoiding a second application registry.

## Hardware or design knob — ready with local change

`pipeline/sweep/design.py` owns supported names, defaults, resolution,
validation, stable slugs, build keys, and sweep grids.  `targets/hetero/system.py`
consumes design values, `pipeline/gen_system_header.py` propagates the resolved
model to runtime headers, and `targets/hetero/soc.py` applies model-specific
GVSoC construction.  `ExperimentRequest.design_overrides` flows through
`resolve_experiment` into resolved hardware identity and `ResourceSummary`.

Add a knob first to `DEFAULTS`, then add source-grounded validation and the
actual target/build propagation.  Add its metadata in
`pipeline/experiment/parameter_catalog.py`; that catalog deliberately rejects
metadata drift.  Update `ResourceSummary` only if the knob changes a resource
the summary can derive from the resolved design.  Finally include every
calibration-relevant source in the calibration input path if the knob changes
measured behavior; calibration fingerprints already include the resolved
design and source set.

`test_parameter_catalog.py`, `test_resolve.py`, `test_resource_summary.py`,
`test_sweep_prepare.py`, and calibration-artifact tests protect the existing
path.  The limitation is that resource derivations are intentionally explicit,
so a new resource fact must be audited rather than inferred from a knob name.

## Kernel implementation — ready with local change

The concrete path is source file and public symbol, image build override in
`pipeline/build_mesh.py`, mailbox/runtime dispatch in `runtime/mesh`, and the
Deeploy binding in `pipeline/hetero_platform`.  Concrete FP32 MatMul/Gemm
paths are recorded by `pipeline/experiment/kernel_implementation_catalog.py`.
After a completed run, `actual_implementation.py` joins generated offload
arguments to runtime beacons and records an implementation ID or explicit
unknown/fallback evidence.

For a new implementation, audit that complete path before assigning an ID;
then add its source/build/dispatch support, catalog entry, source-drift checks,
and actual-evidence rule if it is safely determinable.  Add calibration only
for an implementation/operator pair that is genuinely measured.  Mapper cost
identity remains engine/operator based today: it must not be represented as a
measured rate for a specific implementation unless calibration is extended to
bind that implementation identity.

`test_kernel_implementation_catalog.py` and
`test_actual_implementation.py` protect IDs, sources, fallbacks, and catalog
membership.  Current catalog coverage is intentionally limited to the audited
FP32 MatMul/Gemm paths; the existence of other runtime kernels is not catalog
coverage.

## Mapping strategy — fragile

The stable strategy ID and descriptive metadata live in
`pipeline/experiment/mapping_strategy_catalog.py`; `ExperimentRequest` and
`resolve_experiment` reject unknown IDs and preserve the selected ID in
resolved metadata.  The current operational factory is
`pipeline/hetero_platform/mapper.py::make_mapper`, called by
`pipeline/hetero_platform/generate.py::build_deployer`; mapping explanations
are serialized beside each generated node and then preserved in the run
manifest.

The seam is not yet routine because generation currently constructs only
`make_mapper(pin, host)`: the resolved strategy identity is descriptive and is
not a runtime factory-selection input.  A future strategy must first make the
strategy ID an explicit generator/runner input bound to a vetted factory, then
extend the catalog, request validation, explanation, and manifest tests.
Do not add a catalog row that cannot select the operational mapper.

`test_mapping_strategy_catalog.py`, mapping-explanation tests, mapper-safety
tests, resolver tests, and manifest tests protect the present strategy.  No
factory registry is introduced while there is one operational strategy.

## Simulator or host profile — fragile

`pipeline/build_mesh.py::HOSTS` owns the host image and matching GVSoC target.
`pipeline/experiment/host_profile_catalog.py` derives descriptive profile rows
from it, and resolver validation stores the chosen target in simulator
identity.  `run_hetero.py` builds and launches the selected `HOSTS` target;
calibration records host and simulator target in its fingerprint.

Adding a profile requires a real image/target pair, host-profile metadata,
host rates, CLI/code-generation compatibility, and calibration evidence.  The
current calibration context and sweep launch path still contain the two known
target cases, so a third profile requires a focused audit there rather than
only adding `HOSTS`.  Verify target selection, toolchain/build settings,
calibration identity, and manifest provenance together.

`test_host_profile_catalog.py`, `test_discovery.py`, resolver tests, and
calibration-artifact tests catch catalog and identity drift.  They do not make
a new simulator target valid by themselves.

## Precision — blocked

There is no first-class precision request today.  The current operational path
is FP32-specific: workload inspection reports ONNX tensor dtype and byte size;
cluster compatibility requires FP32 in `engines.py`; kernel symbols, mailbox
job kinds, runtime C sources, calibration workload, implementation IDs, and
mapper rates are named or measured for FP32.  Generator inputs are also
converted through the present FP32-oriented deployment path.

Before adding any FP16, FP8, integer, or mixed-precision feature, introduce an
explicit precision/dtype specification that propagates as:

```text
request
-> resolved experiment
-> workload tensor bytes and working set
-> kernel compatibility
-> engine capability
-> calibration identity
-> mapper cost and rate identity
-> actual implementation evidence
-> measured correctness, accuracy, and error
```

Unknown precision must be rejected, never defaulted to FP32.  This is a
cross-cutting feature and remains out of scope until that propagation can be
implemented and calibrated end to end.

## Future engine — fragile

The authoritative numeric/name identity starts in
`targets/hetero/system.py::ENGINE_NAMES`; runtime beacon macros are in
`pipeline/hetero_platform/progress.py`, and the engine catalog rejects drift
between them.  A new engine must then have a target/model, image and ELF
handling, runtime mailbox/dispatch support, deployment engine and capability
rules, mapper construction and calibrated cost inputs, ResourceSummary
coverage where defensible, kernel catalog/evidence support, and result and
manifest provenance.

The existing catalog checks prevent a silent identity mismatch, but the
operational runtime currently has explicit Snitch/Spatz image, environment,
header, and dispatch handling.  Add an engine only through a focused
end-to-end design; do not make it appear supported by adding catalog metadata
alone.  Validate with engine/discovery tests, mapper tests, kernel/evidence
tests, generated headers, and a real offload integration run.

## Cross-cutting invariants

All extensions retain the requested -> resolved -> actual -> measured
separation.  Resolved catalogs describe the requested configuration; actual
implementation evidence comes only from generated arguments and completed
runtime beacons; calibration and run manifests retain input fingerprints and
source provenance.  Unknown shape, capability, cost, and implementation facts
remain explicit rather than becoming zero, supported, or measured by default.
