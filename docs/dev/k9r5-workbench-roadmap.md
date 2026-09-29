# K9R5 Experimental Workbench Roadmap

## Goal

Evolve K9R5 incrementally into a reproducible and extensible experimental workbench for hardware/software co-design.

The workbench should make it possible to extend hardware parameters, workloads, kernel implementations, mapping strategies, simulator profiles, software stacks, precision, tiling/memory policies, and engines without rebuilding experiment identity, provenance, calibration validity, manifests, and discovery infrastructure for every new feature.

Guiding rule:

> Minimal input, deterministic resolution, explicit ambiguity, fully provenanceable results.

## Core experimental model

Every experiment must keep these layers distinct:

```text
REQUESTED
what the researcher asked for
        ↓
RESOLVED
the complete configuration implied by that request
        ↓
ACTUAL
what software, mapping, kernel implementation and simulator actually executed
        ↓
MEASURED
cycles, correctness, accuracy and other observations
```

## Existing foundation to verify from the actual repository

The current branch is expected to contain most or all of:

- deterministic fingerprint utilities;
- source/dependency provenance;
- calibration metadata and stale-cache detection;
- calibration artifact integrity checks;
- stale runtime/mesh refresh protection;
- run manifest;
- parameter catalog;
- engine catalog;
- host profile catalog;
- stable mapping-strategy identity;
- workload inspection and descriptors;
- `ExperimentRequest`;
- `ResolvedExperiment`;
- deterministic resolver;
- `k9r5_current` platform profile;
- `gui_query` experiment discovery;
- sweep integration with resolved experiment metadata.

Never assume these are present merely because this roadmap says so. Inspect the working tree.

## Remaining foundation milestones

### Milestone 1 — Current state and sweep pin

Verify the actual working tree and complete, only if necessary:

```text
pipeline/sweep/run.py --pin {cva6,snitch,spatz}
```

Preserve the existing semantics: `--pin spatz` forces Spatz-compatible nodes to Spatz; it does not imply that the complete graph runs on Spatz.

### Milestone 2 — ResourceSummary

Add a derived, descriptive summary of architectural resources when defensible:

- physical cores;
- compute PEs;
- control/DMA cores;
- useful compute cores;
- Spatz lanes/FPUs per PE;
- total useful arithmetic resources;
- nominal arithmetic peak with precision stated;
- TCDM size;
- known TCDM bank geometry;
- known memory-path information.

Do not invent area or power numbers.

### Milestone 3 — KernelImplementation catalog

Audit concrete paths:

```text
source
→ symbol
→ build override
→ runtime dispatch
→ fallback
```

Register concrete implementations, not only `engine + op`.

Potential entries must be verified against the actual source before being frozen.

### Milestone 4 — Actual implementation and fallback tracking

Record, when safely determinable:

```text
node → engine → concrete implementation
```

Known fallback behavior must be explicit. Unknown implementation stays `unknown`.

### Milestone 5 — Mapping explainability

Preserve mapper evidence such as:

- strategy;
- selected engine;
- candidates;
- estimated cost;
- rate/cost source;
- pin/constraint influence.

Initially this must not alter engine selection.

### Milestone 6 — Safety hardening

Handle known hazards independently with focused tests:

- dynamic/unknown tensor size must not silently become zero bytes;
- missing engine rate must not silently inherit unrelated CVA6 rates;
- pin semantics must be explicit;
- known tuned-to-generic fallbacks must be recorded or rejected in strict scientific mode.

### Milestone 7 — Extension-seam audit

Verify a clear incremental path for adding:

- workload;
- hardware parameter;
- kernel implementation;
- mapping strategy;
- simulator/profile;
- precision;
- eventually a new engine.

Do not build a generic plugin framework merely to satisfy this milestone.

### Milestone 8 — Full validation

Validate at four levels:

1. unit/structural tests;
2. golden/regression tests;
3. adversarial tests for known failure classes;
4. conceptual/scientific audit of whether abstractions match actual execution.

Passing tests is necessary but not sufficient.

## Out of scope until the foundation is frozen

Unless separately requested, do not implement during these milestones:

- Deeploy tiling integration;
- double buffering;
- new scheduling;
- new engines;
- N-EUREKA;
- `spatz_cluster_v3` migration;
- generic 16/32-bank simulator knob;
- SSR/FREP hardware toggle;
- FP16/FP8/SDOTP integration;
- new topology;
- adaptive DSE;
- generic plugin framework.

## After the foundation

First controlled campaigns should use currently defensible knobs before deeper simulator changes:

```text
Spatz PE/core scaling
↓
Snitch PE/core scaling
↓
Spatz lane scaling
↓
PE × lanes
↓
shape/reuse regimes
↓
normalization studies
↓
TCDM / memory sensitivity
```

Later work may include bank-count studies, outstanding requests, Snitch memory paths, reference simulator profiles, upstream kernels, precision/quantization, tiling, DMA/buffering, and improved mapping strategies.

The objective is not a universal architecture ranking. The objective is to identify regimes and mechanisms that explain when each hardware/software organization performs well or poorly.
