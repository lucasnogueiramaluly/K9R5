# Codex Task — Milestone 6: Safety Hardening

Work directly on the current K9R5 repository opened in this VS Code workspace.

Read and obey:
- `AGENTS.md`
- `docs/dev/k9r5-workbench-roadmap.md`
- `docs/dev/codex-task-milestone-04.md`
- `docs/dev/codex-task-milestone-05.md`

Milestones 1–5 are structurally complete.

Milestone 5 made current mapper behavior explainable without changing policy.
Important caveats exposed by that audit include:
- `_default` operator-rate fallback paths;
- unknown-engine fallback to the CVA6 rate row;
- dynamic/incomplete-shape behavior in `node_macs`;
- zero-default offload overhead values where current tables omit them;
- mapper cost identity can differ from the actual implementation that later
  falls back to Generic.

Milestone 4 already records actual implementation/fallback evidence per completed
run. Milestone 6 must use these findings to harden unsafe or ambiguous behavior,
but only where the repository evidence supports a concrete fix.

Privileged Docker validation remains deferred to the later batched
integration/full-validation pass. Do not ask the user to run Docker commands. If
Docker is inaccessible, record that and continue with all valid non-Docker
checks.

This is an implementation and validation task. Audit first, then implement the
smallest coherent safety changes needed for the current K9R5 foundation.

Do NOT start Milestone 7 or later work.

# Goal

Eliminate or explicitly reject concrete cases where the current experiment
pipeline can silently produce misleading metadata, cost estimates, or execution
claims.

The governing principle is:

    unknown != zero
    unknown != supported
    missing cost != "use CVA6"
    tuned estimate != generic-fallback execution
    compatible-node pinning != whole-graph pinning

Harden only current, evidenced failure modes. Do not redesign the mapper or add a
new optimization policy.

# A. Audit current state before changing anything

Inspect the current implementation and tests for:

1. Dynamic/incomplete tensor shapes:
   - workload byte accounting;
   - working-set accounting;
   - MAC estimation / `node_macs`;
   - mapper cost handling.

2. Missing/unknown cost inputs:
   - missing operator keys;
   - `_default` operator-rate usage;
   - unknown engine/rate-row fallback;
   - absent calibration/table entries;
   - any implicit zero/host substitution.

3. Pin semantics:
   - current compatible-node filtering;
   - metadata already exposed by Milestone 5;
   - CLI/help/schema wording.

4. Tuned-to-generic fallback mismatch:
   - Milestone 3 catalog conditions;
   - Milestone 4 actual fallback evidence;
   - Milestone 5 rate/cost explanation;
   - cases where a tuned engine cost may be used for an invocation that the
     source deterministically sends to Generic.

5. Other silent ambiguity already evidenced by current tests or source.

Do not assume an issue is still present merely because it existed historically.
If a checkpoint issue is already fixed, preserve the fix and add/retain a
regression test rather than reimplementing it.

# B. Dynamic/incomplete shape hardening

The existing workload layer already has tests ensuring unknown tensor sizes do
not silently become zero bytes. Preserve that behavior.

Audit the mapper/MAC path separately.

If a node's required shape-derived cost cannot be computed safely:
- do not silently invent zero work;
- do not silently substitute an unrelated cost;
- represent the cost as unavailable/unknown, or reject the mapping decision if
  the current API cannot make a scientifically defensible choice.

Choose the smallest behavior consistent with existing architecture.

Do not add a symbolic-shape engine or general dynamic-shape framework.

# C. Missing cost/rate hardening

Remove or guard unsafe silent substitutions where they can misrepresent a
mapping decision.

In particular audit:
- unknown-engine -> CVA6-row fallback;
- `_default` operator rates;
- missing measured-rate entries;
- absent overhead rows/fields.

Distinguish between:
- an explicit documented proxy/default that is intentionally allowed;
- a missing value that should make a candidate cost unavailable;
- an engine/operator pair that should be considered unsupported for cost-based
  selection.

Do not convert a missing cost into an arbitrary large number unless that is
already an established project convention and the metadata remains explicit.

If explicit proxy/default behavior is retained for compatibility, require the
mapping explanation to identify it unambiguously and add tests proving it cannot
masquerade as measured calibration.

# D. Tuned estimate vs Generic fallback

This is a primary scientific-validity issue.

For current FP32 MatMul/Gemm cases where the exact runtime arguments
deterministically imply that an engine's tuned implementation will fall back to
Generic, prevent the mapper from silently presenting a tuned-kernel rate as if
it described that execution.

Use the smallest source-grounded solution. Acceptable directions include:
- mark the tuned cost unavailable for that invocation;
- use an explicitly catalogued generic/proxy cost if one genuinely exists and
  its provenance is explicit;
- reject the candidate in a strict/safe mode if no defensible rate exists.

Do NOT invent a Generic performance rate.

Do NOT change kernels merely to avoid fallback.

Do NOT generalize conditions beyond what Milestones 3–4 proved from source.

The final behavior must make it impossible for a deterministic whole-kernel
Generic fallback to be silently priced as the tuned implementation.

# E. Strictness / compatibility

If a strictness control is necessary, prefer the smallest explicit mechanism
consistent with existing request/resolver patterns.

Do not build a generic policy framework.

Any new strict/safe behavior must:
- have a clear default;
- preserve backwards compatibility only where scientifically acceptable;
- be recorded in request/resolved metadata;
- be deterministic;
- be testable without GVSoC.

If no new control is necessary, do not add one.

# F. Pin semantics hardening

Do not change current pin semantics unless source/tests reveal an actual bug.

The current meaning is:

    pin = restrict compatible nodes to that engine where the engine can execute
          them; it is NOT a guarantee that the whole graph executes only there.

Make this explicit wherever a researcher could reasonably misinterpret it:
- CLI help;
- request/schema metadata;
- mapping explanation;
- tests.

Do not convert `--pin` into whole-graph strict pinning in this milestone.

# G. Preserve separations created by earlier milestones

Do not collapse these concepts:

- availability catalog (M3);
- actual implementation/fallback evidence (M4);
- mapping-cost explanation (M5).

M6 may cross-check them for safety, but keep their semantics distinct.

A mapper prediction is not actual execution evidence.
An actual Generic fallback is not proof that a Generic calibrated rate exists.

# H. Tests

Add focused regression/adversarial tests covering, where current source truth
allows:

1. unknown tensor size remains unknown, not zero;
2. unknown/incomplete MAC cost does not become a fabricated numeric estimate;
3. unknown engine/rate row cannot silently borrow CVA6 cost;
4. `_default`/proxy rates, if retained, remain explicitly identified as proxy
   and not measured;
5. missing calibrated/operator cost is explicit and cannot silently select an
   engine through fabricated data;
6. deterministic Snitch tuned->Generic fallback cases are not silently priced
   with a tuned rate;
7. deterministic Spatz tuned->Generic fallback cases are not silently priced
   with a tuned rate;
8. Snitch scalar-tail case remains a tuned implementation case, not a
   whole-kernel fallback;
9. pin semantics remain compatible-node filtering and are explicitly described;
10. existing valid mappings retain their previous selected engine where no
    safety issue applies;
11. mapping explanation remains consistent with hardened behavior;
12. actual implementation evidence remains unchanged in meaning.

Include adversarial cases rather than only happy paths.

# I. Validation

Run every valid check available:
- focused M6 tests;
- existing workload, mapper, mapping-explanation, kernel-catalog, actual-
  implementation, resolver, and manifest tests where host dependencies allow;
- syntax/import checks;
- query/help/schema checks;
- `git diff --check`;
- `git status --short`;
- final diff inspection.

Attempt canonical/integration validation only if Docker is available.
If Docker is inaccessible:
- do not ask the user to run anything;
- do not alter Docker/system permissions;
- record pending integration validation for Milestone 8.

Do not weaken tests or install ad-hoc host dependencies.

# J. Scope exclusions

Do NOT:
- add a new mapper strategy;
- optimize mapper objective;
- implement global scheduling;
- add tiling/double buffering;
- add precision support;
- add new kernels;
- change topology;
- parameterize TCDM bank count;
- migrate Spatz to v3;
- implement generic plugin infrastructure;
- begin the extension-seam audit (Milestone 7).

# K. Public repository hygiene

Keep the result suitable for later GitHub publication:
- no temporary/debug artifacts;
- no prompt/conversation references in permanent source/docs;
- no speculative dead abstractions;
- coherent names and locations;
- no commit, push, PR, or remote changes.

The existing untracked `results/m1-pin-spatz/` directory is a prior validation
artifact. Do not incorporate it into source/tests and do not delete it unless
existing project cleanup policy explicitly makes that safe.

# Final report

Return:
1. safety audit findings, distinguishing already-fixed vs still-active issues;
2. files changed;
3. exact hardened behaviors;
4. dynamic/incomplete-shape policy;
5. missing cost/rate policy;
6. treatment of `_default`/proxy rates;
7. treatment of tuned-to-Generic fallback cost mismatch;
8. final pin semantics/documentation;
9. behavior changed;
10. behavior explicitly not changed;
11. proof that unaffected valid mappings preserve previous selections;
12. focused/adversarial tests and results;
13. pending canonical/integration validation;
14. scientific caveats still remaining after M6;
15. `git status --short`;
16. diff summary including untracked Milestone 6 files;
17. confirmation that no Milestone 7+ work was started;
18. confirmation that no commit/push/PR/remote operation occurred.
