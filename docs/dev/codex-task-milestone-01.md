# Codex Task — Milestone 1: Current State + Sweep Pin

Work directly on the current K9R5 repository opened in this VS Code workspace.

This is an implementation and validation task, not an advisory task. Do not stop after giving a plan or explanation. Inspect the actual repository, make only the changes required below, run tests, repair failures, and finish with a concrete report.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`

## Scope

Implement ONLY Milestone 1. Do not start ResourceSummary or any later milestone.

### A. Baseline inspection

Inspect at minimum:

- `git status --short`
- `git diff --check`
- relevant files under `pipeline/experiment/`
- `pipeline/sweep/run.py`
- `pipeline/run_hetero.py`
- existing tests relevant to experiment resolution and sweep
- current `pipeline/gui_query.py`

Determine what parts of the experimental workbench actually exist in the working tree. Do not assume previous patches were applied.

Do not discard or rewrite existing user changes.

### B. Verify / complete `--pin` support in the sweep

Desired interface:

```text
pipeline/sweep/run.py --pin {cva6,snitch,spatz}
```

The sweep must forward the value into the existing `run_hetero.py --pin` mechanism.

The value must also be represented, where appropriate, in:
- `ExperimentRequest`;
- resolved experiment mapping metadata;
- request/manifest metadata.

Preserve the existing semantics of `run_hetero.py --pin`.

`--pin spatz` does NOT mean the entire graph executes on Spatz. It means Spatz-compatible nodes are forced to Spatz while unsupported nodes may remain elsewhere.

Do not change that behavior in this milestone.

If sweep pin support is already complete, do not rewrite it. Verify it and preserve it.

If incomplete, implement the smallest coherent fix.

### C. Tests

Add or repair focused tests only when necessary.

At minimum verify:

- sweep CLI exposes `--pin`;
- accepted choices are `cva6`, `snitch`, `spatz`;
- value reaches the run-cell execution path;
- value is forwarded to `run_hetero.py`;
- `ExperimentRequest` records it;
- resolved experiment records the intended mapping constraint;
- request/manifest metadata retains it;
- no-pin behavior remains unchanged.

Run:

- relevant targeted tests;
- `git diff --check`;
- the complete Python test suite (`make python-test` if still canonical).

If Docker access is available without changing system configuration, run one minimal existing pinned integration/sanity workload using Spatz and verify:

- status is OK;
- a compatible GEMM/MatMul is placed on Spatz;
- manifest records the pin;
- unsupported nodes are not incorrectly claimed to be on Spatz.

Do not modify machine permissions, Docker configuration, sudoers, groups, or system settings to make this possible. If Docker access is blocked, report it as a blocker.

### D. Final review

Before finishing:

- inspect the final diff;
- check for accidental behavior changes;
- ensure no later milestone was implemented;
- inspect `git status --short`;
- ensure every changed/untracked file is intentional;
- ensure no temporary/debug/generated artifact was left in tracked locations.

Return a final report containing:

1. repository state found;
2. which experimental-workbench components are actually present;
3. files created/modified;
4. whether `--pin` was already present, incomplete, or newly completed;
5. exact behavior changed;
6. behavior explicitly NOT changed;
7. exact tests/commands run and results;
8. integration-test result or concrete blocker;
9. remaining risks/questions;
10. `git diff --stat`;
11. confirmation that no commit/push/PR/remote operation was performed.

Do not proceed to Milestone 2.
