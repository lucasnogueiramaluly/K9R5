# Codex Task — Milestone 8: Full Validation and Foundation Freeze

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`
- `docs/dev/extension-seams.md`
- `docs/dev/codex-task-milestone-06.md`
- `docs/dev/codex-task-milestone-07.md`

Milestones 1–7 are structurally complete.

Milestone 8 is validation/freeze only. Do NOT add new features or begin Phase B
architectural experiments.

Privileged Docker access may remain unavailable inside Codex. Perform every
validation available to you. If Docker is inaccessible, do not change system
permissions and do not ask the user to run commands during the task. Instead,
produce one concise, batched manual integration-validation plan at the end,
containing only the checks that truly require the canonical container.

# Goal

Establish whether the current K9R5 foundation is internally coherent,
reproducible, scientifically defensible, and ready to freeze before Phase B.

Validate the complete contract:

    requested -> resolved -> actual -> measured

including:
- deterministic experiment resolution;
- workload descriptors;
- ResourceSummary;
- source/toolchain/simulator/calibration provenance;
- KernelImplementation catalog;
- actual implementation + fallback evidence;
- mapping explainability;
- safety hardening;
- extension-seam invariants;
- manifest/result serialization;
- sweep behavior and pin semantics.

# A. Validation plan first

Before editing anything, audit the current test and validation surfaces and
write down the validation matrix you will execute.

Classify checks into:

1. unit / pure-Python;
2. structural / serialization;
3. regression / golden;
4. adversarial / safety;
5. integration / canonical-container;
6. scientific invariants.

Do not add new functionality merely to make validation easier.

# B. Full local test pass

Run all tests that are valid in the current environment.

At minimum include, where available:
- experiment resolver/schema tests;
- workload-spec tests;
- parameter/engine/host/mapping/kernel catalogs;
- ResourceSummary tests;
- fingerprint/provenance/calibration tests;
- sweep prepare/pin tests;
- mapping explanation tests;
- mapper safety tests;
- actual implementation/fallback tests;
- run manifest tests;
- extension-seam related invariants.

Do not weaken, skip, or rewrite tests just because a host dependency is absent.
Clearly separate dependency-blocked tests from genuine failures.

# C. Structural consistency audit

Verify, without changing semantics:

1. Stable IDs referenced by run metadata exist in their catalogs.
2. ResourceSummary values are derived from resolved design, not redeclared.
3. Mapping explanations refer to the same strategy identity used by resolver.
4. Actual implementation IDs exist in KernelImplementation catalog.
5. Fallback evidence is consistent with source-proved conditions.
6. Manifest/request/resolved/actual/measured serialization remains deterministic.
7. Calibration/provenance identities are internally consistent.
8. Unknown values remain unknown, not silently converted to zero/default.
9. Pin semantics remain compatible-node filtering, not whole-graph guarantee.
10. No Phase B experimental knob or policy change was accidentally introduced.

# D. Adversarial/scientific invariant checks

Exercise representative edge cases that must remain safe:

- incomplete/dynamic shapes;
- missing operator rate;
- missing engine rate row;
- explicit `_default` proxy rate;
- deterministic Snitch tuned->Generic fallback;
- deterministic Spatz tuned->Generic fallback;
- Snitch scalar-tail case remains tuned;
- incompatible pin;
- compatible pin;
- no safely priced candidate;
- metadata/beacon disagreement for actual implementation evidence;
- stale calibration/provenance mismatch where current tests support it.

The purpose is to prove the foundation fails explicitly rather than silently.

# E. Golden/regression preservation

Inspect the repository for existing golden/reference outputs.

Where the current environment permits, verify that refactor-only foundation work
did not change pre-existing expected operational results.

If a canonical run is required and Docker is unavailable, record the exact
pending golden checks for the batched manual integration plan.

Do not update a golden value merely because the current run differs. Treat a
difference as a regression to investigate.

# F. Git/public-repository hygiene audit

Audit the complete worktree for later GitHub publication.

Check:
- no prompt/chat/Codex references in permanent project source/docs except task
  files that are intentionally developer-local documentation;
- no temp/debug artifacts accidentally added;
- no generated result directories treated as source;
- no secrets, absolute machine-specific paths, or local credentials introduced;
- no accidental binary blobs;
- no build/cache artifacts;
- `git diff --check`;
- final status and complete diff summary, including untracked files.

Do not delete user artifacts unless clearly safe and requested.
`results/m1-pin-spatz/` is a prior validation artifact; classify it, but do not
delete it automatically.

# G. Freeze assessment

At the end, classify the foundation as one of:

- `ready_to_freeze`
- `ready_to_freeze_with_pending_container_validation`
- `not_ready`

Support the classification with concrete evidence.

If `not_ready`, fix only defects that are clearly regressions or violations of
the already-defined M1–M7 contracts. Do not expand scope.

If a fix is required, re-run the affected validation.

# H. Canonical-container validation handling

If Docker works in your environment, run the canonical integration checks
yourself.

If Docker does NOT work:
- do not alter Docker/system permissions;
- do not ask for repeated manual commands during the task;
- return ONE batched manual validation script/command plan at the end, covering
  only canonical-container checks still required.

That pending plan should include, if applicable:
- full `make python-test`;
- one baseline resolved-experiment query;
- one override query proving ResourceSummary causality;
- one pinned Snitch run;
- one pinned Spatz run;
- at least one deterministic tuned->Generic fallback run;
- manifest inspection proving requested/resolved/actual/measured continuity;
- golden/reference regression run(s).

Keep the manual plan minimal and executable as a single batch where practical.

# I. Scope exclusions

Do NOT:
- begin PE/core/lane sweeps;
- add new knobs;
- add new kernels;
- add new mapper strategies;
- implement precision support;
- add tiling/double buffering;
- parameterize bank count;
- migrate Spatz to v3;
- add future engines;
- implement a plugin framework;
- perform Phase B experiments.

# J. Final report

Return:

1. validation matrix actually executed;
2. all local test results;
3. dependency-blocked checks;
4. structural consistency findings;
5. adversarial/scientific invariant findings;
6. golden/regression status;
7. public-repository hygiene findings;
8. any fixes made during M8;
9. exact remaining caveats;
10. freeze classification;
11. exact Phase B entry conditions after freeze;
12. pending canonical-container validation, if any;
13. one batched manual validation plan if Docker is inaccessible;
14. `git status --short`;
15. complete diff summary including untracked foundation files;
16. explicit confirmation that no Phase B experiments/features were started;
17. confirmation that no commit/push/PR/remote operation occurred.
