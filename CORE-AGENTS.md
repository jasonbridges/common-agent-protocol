# Universal Multi-Agent Operating Contract (CORE-AGENTS.md)

This document specifies the normative, project-independent operating contract for coding agents working across repositories. Consuming repositories mount this specification as a git submodule at `.agents/` and define project-specific invariants, architecture constraints, and build/validation commands in their local `AGENTS.md`.

---

## 1. Document Authority and Conflict Resolution

When two artifacts, specifications, or requirements conflict, agents must resolve precedence in this order unless explicitly superseded by an accepted Architectural Decision Record:

1. **Accepted ADRs** in `docs/adr/`
2. **Security & Governance Policies** in `policy/` or `.agents/`
3. **Versioned Specifications & Schemas** in `docs/specifications/`, `docs/architecture/`, and `schemas/`
4. **Component Designs & Runbooks** in `docs/design/` and `docs/`
5. **Issue Requirements & Acceptance Criteria**
6. **Existing Implementation Behavior**

**Strict Resolution Rule:** Do not silently resolve contradictions. If a requested issue implementation conflicts with an accepted ADR or repository policy, do not work around it or silently pick one interpretation. Amend or supersede the architecture explicitly before writing production code.

---

## 2. Mandatory Ordered Context Loading

To prevent context exhaustion, token waste, and hallucinated designs, agents **must not begin by browsing the whole repository**. Load context strictly in this sequence:

1. The repository's root `AGENTS.md` (and this `CORE-AGENTS.md` specification)
2. The assigned GitHub issue / task description and its full comment history
3. Referenced implementation plans, designs, specifications, and schemas
4. Referenced ADRs and security policies
5. Confirm all declared dependencies are complete on `main`
6. Only then inspect implementation packages and tests touched by the planned change

The issue/task should contain enough authoritative references that an agent does not have to invent architecture. If an architectural decision is missing, resolve the design artifact first.

---

## 3. Safe Defaults for Ambiguity

When an implementation detail is unspecified by the task, issue, or ADR:

1. **Choose least-privileged behavior:** default to lowest system privileges, restricted network access, and narrowest interfaces.
2. **Choose deterministic behavior:** avoid random seeds, unordered map iterations, or race-prone time checks where practical.
3. **Fail closed on security boundaries:** deny access when authorization or policy evaluation is ambiguous.
4. **Prefer explicit configuration over environment discovery:** require explicit configuration rather than guessing host topology.
5. **Avoid unvetted third-party dependencies:** prefer standard libraries or small, well-maintained dependencies.
6. **Record material open questions:** log unresolved architectural questions in `docs/UNRESOLVED.md` rather than making undocumented assumptions.

---

## 4. Forbidden Shortcuts Blacklist

Never satisfy a failing test, linter, or CI gate by:

- Disabling, deleting, or skipping a failing test without explicit documented justification
- Broadening host, daemon, container, or sudo execution privileges
- Bypassing network policies or opening unauthorized host ports
- Hardcoding workstation-local home paths (e.g. `/var/home/...`) into packaged units or committed code
- Switching to mutable image tags or ignoring checksum/digest validation failures
- Swallowing lease, state transition, or lock errors
- Logging secrets, credentials, API keys, or session tokens
- Turning off transport encryption or disabling TLS certificate validation
- Mutating untracked system state out-of-band to artificially pass verification

---

## 5. Work Claiming and Atomic Branch Reservation

To prevent multi-agent collisions and stranded work:

1. **Verify dependencies:** Confirm that all task/issue dependencies declared in the issue or task DAG are merged into `main`.
2. **Search active work:** Search GitHub for open issues, active branches, and open pull requests for the task ID.
3. **Atomic claim via Git ref:** Creating the canonical branch (e.g., `feature/TASK-XXXX-<short-description>` or `work/issue-N`) from current `main` HEAD is the **authoritative claim operation**. If the branch ref already exists on `origin`, the task is claimed. Do not start work; select another unclaimed task.
4. **Record claim in issue:** Immediately post a claim comment on the corresponding issue:
   ```text
   Task: <TASK-ID or Issue-N>
   Status: claimed
   Owner: <agent-id>
   Branch: <canonical-branch-name>
   Dependencies: <dependencies>
   ```
5. One numbered task or issue has one active implementation owner by default. Do not begin overlapping work on a task already claimed by another active agent.

---

## 6. Scope Ownership and Path Collision Rules

Every implementation issue must contain a `## Scope ownership` heading (casing is strict: do not use `Scope Ownership` or `## Scope`).

Declare `Exclusive:` and `Shared:` path patterns beneath that heading:

```markdown
## Scope ownership

Exclusive:
• `pkg/scheduler/**`
• `internal/postgres/lease_test.go`

Shared: none
```

- **Exclusive paths:** Owned by exactly one active task branch at a time.
- **Shared paths:** Central files (such as central build configs, shared schema definitions, or common migrations) require sequencing. Sequence small, independent PRs rather than attempting parallel edits.
- **Collision Rules:**
  - Before starting and before opening a PR, inspect open PR changed paths for overlap.
  - Overlapping changes to identical files without coordination are treated as collisions.
  - If concurrent edits are strictly necessary, **both** issues must carry reciprocal exception lines:
    ```text
    Coordination-Exception: #<OTHER_ISSUE>
    ```
    Validation fails if only one issue lists the exception.

---

## 7. Durable Project Status Updates

GitHub is the durable project record. Chat messages, local scratch notes, and agent working memory are not substitutes for updating the owning issue and PR. Keep status current enough that another agent or the maintainer can resume work without reconstructing the session.

Post or update GitHub status when any of these occurs:

- **Claim / Start:** Comment on the issue with the task branch, base SHA, intended paths, dependencies, and known constraints.
- **Scope or Design Change:** Update the issue body and scope declarations before editing files outside initial scope; record new dependencies or ADR decisions when known.
- **Material Blocker or RCA:** Record the concrete blocker, failure logs, workflow run/job IDs, affected dependency, safe failure mode, and next unblocking action on the issue or PR. Do not leave the only root cause analysis in chat.
- **PR Opened or Materially Revised:** Keep the PR body current with changed paths, verification commands, operational rollback, and security/execution-policy impact. A PR body is a living summary, not a creation-time snapshot.
- **Ready for Review:** Only mark ready after criteria, local tests, and exact-head CI gates pass.
- **Blocked after Review / CI:** Return the PR to draft; document whether the blocker is owned by this issue or an upstream dependency.
- **Merge / Completion:** Ensure the canonical issue is closed by the PR (`Closes #NNN`) and verify follow-up tasks are represented in the milestone roadmap.

Status updates must be concise and evidence-based: prefer commit SHAs, test targets, workflow run IDs, and exact issue/PR numbers over generic statements like "still working".

---

## 8. Milestone Tracking and Parity

GitHub issues are the work queue and milestone source of truth.

1. **Mandatory Milestone Assignment:** Every implementation issue must be assigned to an active delivery milestone before implementation work is claimed.
2. **Issue / PR Milestone Parity:** The canonical task PR must carry the **same milestone** as its tracking issue. Do not leave implementation PRs unmilestoned, and do not assign a PR to a different milestone to make dashboard progress look cleaner.
3. **Milestone Lifecycle:**
   - Select the milestone on the issue **before** creating the task branch.
   - When planning intent changes, update the issue milestone first, then immediately update the canonical PR to match and document the reason in an issue comment.
   - Before marking a PR ready for review, verify issue/PR milestone parity.
   - Milestone completion is driven by merged PRs and closed issues, not by ad-hoc status prose.

---

## 9. Pull Request Protocol and Review Readiness

1. **Draft PRs:** Opening a draft PR (`gh pr create --draft`) is permitted while work is in flight, during active multi-commit implementation, or while initial validation is underway.
2. **Promotion to Ready for Review:** An agent must not leave a completed task sitting in Draft status. Once:
   - all task acceptance criteria are satisfied and checked off in the PR and tracking issue;
   - repository validation passes;
   - local formatting, static analysis, and tests pass;
   - milestone parity between issue and PR is verified; and
   - canonical exact-head CI workflows are green;
   the implementing agent **MUST** mark the PR ready for review:
   ```bash
   gh pr ready <PR-NUMBER>
   ```
3. **Reviewer Request:** Request `jasonbridges` as reviewer when the PR is bot-authored, and verify via `gh pr view <n> --json reviewRequests` that the request exists.
4. **Issue Synchronization:** Update the associated task issue body or comment with `Status: review`.

---

## 10. Agent Identity and Reviewer Trap

Agents commit as the GitHub App `jasonbridges-agent`, not as the maintainer. Activate at session start:

```bash
eval "$(~/.config/gh-app/agent-env.sh)"    # git identity + fresh GH_TOKEN
```

That exports `GIT_AUTHOR_*` / `GIT_COMMITTER_*` and mints a **one-hour** installation token. Mint on demand; never cache one — a stale token fails as `Bad credentials`.

**Environment-scoped on purpose:** The workstation is shared with the maintainer, whose global git identity is their own. Setting `user.name` / `user.email` globally or per-repository would rebrand the maintainer's commits as an agent's.

Two critical measured invariants:

- **Reviewer request author trap:** GitHub refuses a review request naming the PR *author* (`HTTP 422`). `gh pr edit --add-reviewer` **swallows that 422 and exits 0**. Always verify reviewer assignment via `gh pr view <n> --json reviewRequests`; never trust the command exit code. PRs opened by the GitHub App bot can request the human maintainer normally.
- **Ordinary CI does not commit:** Continuous integration workflows do not author repository commits.

---

## 11. Two-Tier Task Staleness Detection and Reclamation

A task or claim is considered **stale** under two conditions:

- **Deterministic state staleness (fails validation):**
  - An issue is marked `Status: blocked` even though all declared dependencies have merged into `main`.
  - An issue is marked `Status: claimed`, `in-progress`, or `review` while declared dependencies remain incomplete.
  - An issue records a branch that no longer exists on `origin`.
  - An issue claim remains active after its corresponding pull request has already merged.
- **Activity staleness (advisory / eligible for reclamation):**
  - An issue marked `claimed` has no associated branch, commits, or PR created within **48 hours**.
  - An issue or PR marked `in-progress` or `review` has had **no commits, comments, or PR activity for 72 hours** (3 days).

### Reclaiming a Stale Task
When an agent encounters a ready task held by an inactive or stale claim:
1. Verify inactivity across branch and PR history.
2. Do not force-push or adopt abandoned branches directly; create a clean branch from current `main`.
3. Post a formal reclamation notice comment on the issue before modifying code.
4. Update the issue header with the new owner and branch.

---

## 12. Task Completion Rules (Definition of Done)

A task or issue implementation is complete only when:

- All acceptance criteria declared in the issue/task are satisfied and checked off.
- Required local unit, integration, and regression tests exist and pass.
- Documentation, architecture records, runbooks, and schemas are synchronized.
- Repository quality gates and linters pass cleanly.
- No unresolved TODO introduced by the change is required for correctness.
- The PR documents rollback and operational notes explicitly.
- The pull request is marked ready for review (`gh pr ready <PR-NUMBER>`).

Do not mark an issue complete or a PR ready for review merely because code compiles without syntax errors.

---

## 13. Remote Agents and Command Broker Protocol

Remote agents lacking access to `~/.config/gh-app/agent-env.sh` must not use personal access tokens or push directly through maintainer identities.

Where deployed, remote agents interact via the declarative GitHub App Command Broker using immutable signed/hidden comment envelopes:
- **Planning Commands:** Submitted to planning queue issues (`plan.create_issue`, `plan.assign_milestone`).
- **Implementation Commands:** Submit staged, content-addressed Git blobs to atomically claim the task branch, create bot-authored commits, open canonical PRs, and request review.
- **Iterative Updates:** Follow-up commits must use atomic updates referencing the expected parent commit SHA (`expected_head_sha`).
- **Failure Recovery:** If a broker transaction fails after branch creation, recover via explicit provenance verification (`work.resume`) rather than recreating or force-pushing.

---

## 14. Break-Glass Emergency Procedure

Emergency production recovery that bypasses normal PR review is restricted to repository owners and operators:

1. File a tracking issue describing the incident and why the normal path was bypassed.
2. Record the exact commit SHA applied to `main`.
3. Validate the resulting environment and run all repository test suites.
4. Open a post-incident reconciliation PR to restore branch alignment and audit provenance.
5. Remediate the underlying condition that required the bypass.
