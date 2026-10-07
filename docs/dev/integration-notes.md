# Experimental Foundation integration notes

This is maintainer-facing integration history. It records how the historical
Foundation was semantically ported into current M4IA; it is not the primary
user tutorial. Start with the [Experimental Workbench](../experimental-workbench.md)
for current use and [Foundation checkpoints](foundation-checkpoints.md) for the
older M1–M9 construction record.

## Two source lineages

```text
Frozen Foundation
historical base 6d40999
  -> M1-M8 freeze 45bbb7d
  -> M9 provenance hardening e97b2dc
  -> frozen lucas-ic ab188c0

Current M4IA integration base
upstream/main 7cd4aa3
  -> current runners, GUI, target/runtime and new memory subsystem
  -> semantic integration commits d948925..c24c4e7
```

The port was intentionally not a wholesale cherry-pick. Current operational
M4IA behavior won every conflict. Frozen code and documents supplied methods,
invariants, and historical rationale.

## Integrated checkpoints

| Checkpoint | Commit | Maintainer meaning |
|---|---|---|
| CP1 | `d948925` | Strict request/schema, catalogs, deterministic resolution, `m4ia_current`, explicit memory identity |
| CP2 | `8f3a9b3` | Query-only `experiment-schema` and `resolve-experiment` bridge |
| CP3 | `405964a` | Safe unavailable costs, strict rate tables, audited Generic fallback pricing |
| CP4 | `05e63ef` | Mapping explanations, generated arguments, pure implementation evidence |
| CP5 | `c3d1d8d` | Workload-independent calibration identity, C++-aware causal provenance, sidecar contract |
| CP6 | `2a5d909` | Completed-runtime evidence joined in the real runner; effective fixed memory explicit |
| CP7 | `d24e767` | Machine/cell identity, strict calibration reuse, stale-state protection, run manifests |
| GUI/API gate | `c24c4e7` | Explicit GUI Compare `--dram fixed`; backend judged ready for later schema-driven consumption |

## Important adaptations from the frozen branch

### Current product and platform identity

The experiment-facing platform is `m4ia_current`; no compatibility alias was
needed for the unreleased historical platform name.

### Five evidence stages

The port names generated evidence explicitly:

```text
REQUESTED -> RESOLVED -> GENERATED -> ACTUAL -> MEASURED
```

This prevents mapping/dispatch artifacts from being mistaken for completed
execution and prevents completed implementation identity from being inferred
from measured cycles.

### Main memory

The frozen Foundation predated current public main memories. The port derives
the supported choices from current operational sources:

```text
fixed  lpddr4  lpddr4x  lpddr5  hyperram
```

Memory is explicit resolved/machine/calibration/run identity. Omitted and
explicit `fixed` canonicalize identically; operational overrides affect
identity when present. `design.slug` remains numeric chip-design-only.

### Provenance

Current simulator behavior includes causal `.cpp`/`.hpp` sources. The source
sets include relevant DRAM/timing-cache C++ code, select host adapters and
modeled-device files conditionally, and exclude generated defaults that are
deterministically overwritten. Documentation, GUI, tests, and work outputs are
not semantic run inputs.

### Calibration and sweep artifacts

The current CP5 API `capture_calibration_context(root, resolved_experiment)` is
authoritative. CP7 aligned resolved host, calibration host image, GVSoC target,
and parser; validated sidecar internals before reuse; separated host/memory
machine paths; refreshed copied mesh content; and invalidated stale result and
manifest files before reruns.

### GUI boundary

The Rust GUI still has hard-coded UI enums. The accepted gate fixed the one
immediate semantic hazard by always passing Compare memory explicitly,
including `fixed`. A later frontend can replace duplicated choices with:

```text
experiment-schema -> request -> resolve-experiment preview
                  -> run/sweep -> manifest/result
```

That migration is frontend work, not a remaining backend identity design.

## Compatibility deliberately preserved

- Current M4IA runners, target/runtime, kernels, Deeploy integration, and
  memory behavior remain operational truth.
- `design.slug` is still numeric-design-only.
- Direct `--pin` is compatible-node preference; current sweep CLI has no
  sweep-level pin.
- `result.json` keeps the outer `op` / `mapping` / `result` contract.
- Existing sweep row fields remain; identity fields are additive.
- Current area and energy code did not change.
- `area_au` remains a structural relative proxy.
- `cache_dynamic_pj` remains cache dynamic energy, not total SoC energy.

## Validation record

The accepted CP7 review ran 170 Python tests: 167 passed and three
ONNX-dependent tests were skipped. It also recorded 75 focused CP7 tests
passing and `git diff --check` passing. Real Deeploy/GVSoC calibration and
simulation were environment-limited rather than claimed.

The GUI/API gate ran eight `test_gui_query` tests and a 46-test focused
query/identity/resolution/schema/manifest set with no failures. A live schema
query and malformed-request error path passed. Rust tests were not run because
the environment had no Rust toolchain; source review did not substitute for a
claim that they executed.

Documentation-only validation checks links, commands, and regressions; it does
not replace validation in a complete Deeploy/GVSoC execution environment.

## Why historical documents remain separate

The Portuguese development report and heterogeneous-mesh proposal preserve
project rationale and chronology. The Foundation checkpoints preserve
construction attribution and historical validation. This document covers the
modern semantic port. Keeping those roles separate avoids rewriting history as
current operations while retaining maintainer knowledge.
