# Codex Task — Milestone 7: Extension-Seam Audit

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`
- `docs/dev/codex-task-milestone-05.md`
- `docs/dev/codex-task-milestone-06.md`

Milestones 1–6 are structurally complete.

Milestone 6 hardened current safety behavior:
- unknown working sets are not treated as zero;
- incomplete MAC estimates do not become fabricated numeric cost;
- unknown engines do not borrow CVA6 rates;
- missing rows/operator rates/cluster overheads are unavailable;
- external `HES_RATES` rows replace rather than silently merge committed rows;
- deterministic whole-kernel Generic fallback cases are not priced with tuned rates;
- automatic mapping ignores unavailable-cost candidates;
- compatible-node pin semantics remain explicit and unchanged.

Privileged Docker integration remains deferred to Milestone 8. Do not ask the user
to run Docker commands. If Docker is unavailable, record that and continue with
all valid non-Docker checks.

This is an audit + minimal-hardening milestone.
Do not build a plugin framework.
Do not start Milestone 8 validation work.

# Goal

Verify that the current K9R5 foundation has clear, local, non-fragile extension
paths for the dimensions we expect to add after the foundation is frozen.

The milestone must answer:

    "If a researcher adds one new workload, one new hardware knob, one new
    kernel implementation, one new mapping strategy, one new simulator/profile,
    one new precision, or one future engine, where exactly does that extension
    enter the system and which existing invariants/tests protect it?"

The goal is NOT to implement those future features now.
The goal is to ensure the current architecture does not force unrelated invasive
changes for each extension.

# A. Audit the extension seams

Audit at minimum these extension classes:

1. Workload/model
   - ONNX workload discovery/specification
   - descriptors
   - resolver/request path
   - sweep/model selection
   - manifest/provenance implications

2. Hardware/design knob
   - current knob discovery/catalog
   - validation
   - resolved design
   - ResourceSummary derivation
   - build/runtime propagation
   - fingerprint/calibration implications

3. Kernel implementation
   - source/build override path
   - KernelImplementation catalog
   - actual-implementation/fallback tracking
   - relationship to mapper cost identity

4. Mapping strategy
   - strategy catalog
   - resolver/request identity
   - construction/factory seam
   - mapping explanation
   - manifest identity

5. Simulator / host profile
   - simulator identity
   - host profile catalog
   - build target/profile discovery
   - provenance/calibration identity

6. Precision
   - identify the seam required for a future first-class precision/dtype spec;
   - DO NOT implement FP16/FP8/INT8 support;
   - identify which current assumptions are FP32-specific and where future
     precision would need to propagate:
       request -> resolver -> workload bytes -> kernel compatibility ->
       engine capability -> calibration -> mapper -> actual implementation ->
       measured accuracy/error.

7. Future engine
   - engine catalog/discovery
   - canExecute/capability
   - mapper construction
   - ResourceSummary
   - kernel catalog
   - simulator/build integration
   - provenance/calibration
   - manifest/result surfaces

# B. Classify seams

For each extension class, classify the current seam as one of:

- `ready`: a new instance can be added through a clear, local path with existing
  invariants/tests;
- `ready_with_local_change`: one or a few clearly scoped locations need changes,
  but no cross-cutting redesign is required;
- `fragile`: the current architecture still requires unrelated/manual changes in
  several places or relies on duplicated identity;
- `blocked`: no defensible extension path exists yet.

Use project-appropriate names if better, but preserve the distinction.

Do not label something `ready` merely because it is technically possible.
The classification must be supported by source audit.

# C. Minimal fixes allowed

If the audit finds a concrete seam defect that is:
- small;
- clearly within foundation scope;
- required to avoid duplicated/manual identity;
- testable locally;
then fix it.

Examples of acceptable small fixes:
- one missing discovery/catalog bridge;
- one duplicated stable ID that should be derived from an existing source;
- one missing resolver hook;
- one missing invariant/drift test;
- one metadata path that prevents a future extension from appearing in manifests.

Do NOT expand scope into feature implementation.

# D. Explicitly out of scope

Do NOT implement:
- a generic plugin framework;
- dynamic registry loading;
- entry points;
- config-driven arbitrary extension loading;
- new hardware engines;
- new precisions;
- new kernels;
- new workloads merely for demonstration;
- new mapper strategies;
- new topology;
- TCDM bank-count parameterization;
- tiling;
- double buffering;
- N-EUREKA;
- Spatz v3 migration;
- adaptive DSE.

This milestone is about seam quality, not extensibility theater.

# E. Deliverable

Create a concise project document in an appropriate existing documentation area,
for example:

    docs/dev/extension-seams.md

Use the actual repository structure and choose a coherent location/name.

For each extension class, document:
- current entry point(s);
- stable identities involved;
- required propagation path;
- invariants/tests protecting the path;
- seam classification;
- known limitation;
- exact next step when that extension is eventually implemented.

Keep it useful to a future researcher. Do not mention Codex, prompts, chats, or
this milestone task in permanent project documentation.

# F. Tests / invariants

Add or strengthen focused tests only where the audit finds a real invariant that
is currently unprotected.

Potential invariants include:
- catalog IDs match operational sources;
- resolver accepts only discovered/registered identities;
- adding a design knob cannot silently skip resolved serialization;
- ResourceSummary derives rather than redeclares operational values;
- mapping strategy identity is stable and not duplicated manually;
- kernel implementation IDs referenced by actual evidence exist in the catalog;
- host profile / engine catalogs refuse drift;
- unknown future precision is rejected explicitly rather than defaulting to FP32.

Do not add speculative tests for features that do not exist.

# G. Precision-seam requirement

Precision is important but remains out of scope for implementation.

The audit must explicitly identify current FP32 assumptions and the future path
for a first-class precision spec.

The permanent documentation should make clear that precision must eventually
propagate through:

    request
    -> resolved experiment
    -> workload tensor bytes / working set
    -> kernel compatibility
    -> engine capability
    -> calibration identity
    -> mapping cost/rate identity
    -> actual implementation
    -> measured correctness/accuracy/error

Do not add fake support flags or pretend FP16/FP8 exist.

# H. Validation

Run all valid local checks:
- focused seam/invariant tests;
- existing catalog/discovery/resolver tests where host dependencies allow;
- syntax/import checks;
- documentation/link/path checks as practical;
- `git diff --check`;
- `git status --short`;
- final diff inspection.

Attempt Docker/canonical validation only if Docker is already accessible.
If Docker is inaccessible:
- do not ask the user to run anything;
- do not change system/Docker permissions;
- record pending integration validation for Milestone 8.

Do not weaken tests or install ad-hoc dependencies.

# I. Public repository hygiene

Keep the repository suitable for later GitHub publication:
- no temp/debug files;
- no prompt/chat/Codex references in permanent code/docs;
- no speculative plugin scaffolding;
- coherent names and locations;
- no commit, push, PR, or remote changes.

The existing `results/m1-pin-spatz/` artifact is not source. Do not incorporate it
into code/tests and do not delete it unless existing cleanup policy explicitly
makes that safe.

# Final report

Return:
1. extension-seam audit summary;
2. seam classification for workload, hardware knob, kernel, mapping strategy,
   simulator/host profile, precision, and future engine;
3. files changed;
4. minimal seam fixes made, if any;
5. new/strengthened invariants and tests;
6. precision-specific future propagation path;
7. remaining fragile/blocked seams;
8. behavior changed;
9. behavior explicitly not changed;
10. focused tests/results;
11. pending integration validation;
12. `git status --short`;
13. diff summary including untracked Milestone 7 files;
14. confirmation that no Milestone 8 work was started;
15. confirmation that no commit/push/PR/remote operation occurred.
