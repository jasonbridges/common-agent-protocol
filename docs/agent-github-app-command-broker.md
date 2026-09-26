# Agent GitHub App command broker

## Purpose

The command broker gives remote maintainer-authorized agent tooling a narrow way to create normal issue-scoped work while preserving the repository's canonical GitHub App identity. The remote tool stages content-addressed Git blobs with its existing GitHub connection, then asks a trusted default-branch workflow to assemble those blobs into `work/issue-N`, a commit, and a pull request as `jasonbridges-agent[bot]`.

The remote GitHub connection is therefore a preparation and command-submission channel, not the privileged repository-writing identity. It may inspect repository state, stage immutable blobs, and submit the declarative broker request. The trusted workflow separately authenticates as the GitHub App only after validating that request.

The broker does **not** provide a reusable GitHub token to the caller. The App private key remains in GitHub Actions secret storage, the installation token exists only for the broker job, and candidate contents are never executed by the broker.

## Trust model

The workflow accepts commands only from an `issue_comment` when the comment author is exactly `jasonbridges` with GitHub `OWNER` association. Initial work, `work.update`, and `work.resume` commands originate from their canonical open implementation issue. Planning commands originate only from persistent planning queue issue #377. A request is rejected before App-token minting unless it satisfies its closed operation schema and all operation-specific coordination rules.

The request is bound to:

- the issue receiving the comment;
- the exact current `main` SHA;
- the canonical `work/issue-N` branch, which must not already exist;
- the issue's `## Scope ownership` paths;
- immutable Git blob SHAs and allowlisted regular/executable file modes;
- the current open-PR collision state and reciprocal coordination exceptions; and
- a complete PR body satisfying the repository metadata contract.

Immediately before mutation, the bot-authenticated execution stage re-fetches the source comment, verifies its SHA-256 digest has not changed, and re-runs the remote-state checks. An edited command must be replaced with a new comment.

## Safety restrictions

The broker rejects `.github/workflows/**` changes through both initial and iterative work operations. Workflow/control-plane evolution must use the existing local `agent-env.sh` bot path and ordinary human review. This keeps the broker token at `contents: write`, `issues: write`, and `pull-requests: write`; it does not need GitHub `Workflows` permission.

The broker cannot:

- write or force-update `main`;
- choose a noncanonical work branch;
- merge or approve a PR;
- target another repository;
- run arbitrary shell supplied by the command;
- execute staged candidate blobs;
- bypass issue scope/collision validation; or
- automatically erase a claim branch after a partial broker failure.

If the canonical branch has been atomically claimed and a later Git operation fails, the branch is deliberately preserved and a bounded failure comment is posted. Owner/coordinator reconciliation is required; automatic overwrite/retry would violate the claim protocol.

## Command format

The comment begins with the exact line:

```text
/agent-commit-v1
```

New requests should hide the machine envelope in a Markdown HTML comment so normal issue discussions render only the command marker:

```text
/agent-commit-v1
<!-- agent-command-envelope:v1:<base64url(JSON)> -->
```

The payload is compact JSON encoded with URL-safe base64 and without trailing `=` padding. Hidden means presentation hygiene, not confidentiality: raw/API views retain the complete comment for audit, and commands must never contain credentials or secret material. The broker temporarily accepts the legacy raw-JSON form for migration/recovery.

Decoded request example:

```json
{
  "version": 1,
  "issue": 362,
  "base_sha": "0123456789abcdef0123456789abcdef01234567",
  "commit_message": "fix(deploy): keep keyring validation privileged (#362)",
  "files": [
    {
      "path": "deploy/manifest.json",
      "sha": "89abcdef0123456789abcdef0123456789abcdef",
      "mode": "100644"
    }
  ],
  "pr": {
    "title": "fix(deploy): keep keyring validation privileged (#362)",
    "body": "## Issue\n\nCloses #362\n..."
  }
}
```

`sha: null` represents deletion of an issue-owned regular file. Accepted modes are `100644` and `100755`. Requests are bounded by file count, path length, per-blob size, aggregate blob size, comment size, decoded-envelope size, commit-message size, and PR metadata size. The integrity check covers the complete raw comment body, including the visible marker and hidden envelope.

## Broker v2 operations

Broker v2 keeps the same visible `/agent-commit-v1` marker and hidden envelope transport. Version-2 payloads add an explicit `operation` and use closed schemas; unknown operations or fields fail closed. Broker v1 initial-create payloads remain accepted during migration.

The allowed v2 capability surface is finite:

- `plan.create_milestone`
- `plan.create_issue`
- `plan.update_issue`
- `plan.assign_milestone`
- `work.update`
- `work.resume`

There is no generic REST/GraphQL forwarding operation.

### Planning queue

All `plan.*` commands must be posted to issue #377. The queue remains open and is a command/audit surface, not an implementation claim.

Concurrency is scoped to the authorized broker **job**, not the whole `issue_comment` workflow run. The job-level authorization check runs before an event can enter a broker concurrency group, so bot-generated claim/success/failure comments, ordinary discussion comments, and other unauthorized events are skipped without occupying or replacing pending authorized work.

Authorized planning commands use a per-comment GitHub Actions concurrency key. This is deliberate: GitHub retains only one running and one pending run for a concurrency group, so sharing one group for every #377 command can replace an older pending command during a multi-agent burst. Distinct owner planning comments may therefore execute concurrently, while every authorized command on a canonical implementation issue continues to share that issue's concurrency key and remains serialized.

Concurrent planning remains bounded by operation-level validation rather than scheduling order. `plan.update_issue` uses expected body/title state, milestone assignment is limited to existing open resources, and create operations remain closed-schema with their existing duplicate/state checks. A stale or conflicting planning request fails closed and must be refreshed; the broker does not silently reconcile it.

`plan.create_milestone` is create-only. It accepts a bounded title, optional bounded description, and optional timezone-qualified ISO-8601 due date. It rejects a duplicate open milestone title and has no close/delete/update authority.

`plan.create_issue` creates an open issue with bounded title/body and an optional existing open milestone. The caller explicitly declares whether the issue is implementation work. Implementation issues must contain the canonical `Summary`, `Acceptance criteria`, `Scope ownership`, `Validation`, `Rollback`, `SSO impact`, and `Coordination` sections and usable Exclusive/Shared scope ownership.

`plan.update_issue` changes only title and/or body on an existing open non-PR issue. It requires the expected SHA-256 of the current body and, when changing the title, the exact expected current title. It cannot close the issue or mutate labels, assignees, permissions, repository settings, or other fields.

`plan.assign_milestone` assigns an existing open non-PR issue to an existing open milestone. It does not modify or close the milestone.

### Iterative `work.update`

`work.update` is posted to the canonical implementation issue after its initial PR exists. The caller supplies the exact expected head SHA, commit message, and bounded file set; it may optionally replace the PR title/body.

Before mutation the broker requires:

- canonical branch `work/issue-N` already exists;
- the branch head exactly matches `expected_head_sha`;
- exactly one open PR uses that branch, comes from this repository, targets `main`, and closes issue N;
- the issue remains open with usable scope ownership;
- changed paths remain in scope;
- open-PR collision checks still pass, excluding only the PR being updated;
- staged bytes pass the same SHA/size/materialization checks as initial work; and
- `.github/workflows/**` remains denied.

The new commit has exactly one parent: `expected_head_sha`. The broker advances the canonical branch with `force=false`. A stale head is an optimistic-concurrency failure; the broker never auto-rebases or force-pushes. Optional PR metadata changes are limited to validated title/body. Base/head, merge state, approvals, and review history are outside broker authority.

### Initial-work claim provenance and `work.resume`

New initial broker claims contain a hidden machine-readable provenance record in the bot-authored `BOT CLAIM` comment. It binds the claim to:

- issue and canonical branch;
- requested base SHA;
- source comment ID and complete raw-comment SHA-256;
- canonical request SHA-256; and
- intended changed paths.

The provenance contains no secret material and is part of the GitHub audit record.

`work.resume` is only for a broker-created partial initial transaction. The resume command identifies the original immutable source comment/request and supplies the exact currently observed canonical branch head. The broker re-fetches the original owner comment, verifies both digests, verifies the bot claim provenance, and re-runs current scope/collision checks.

Allowed states are intentionally narrow:

- **branch at original base, no PR:** recreate the exact requested blobs/commit and advance non-force;
- **branch one verified bot commit above the original base, no PR:** create the original PR and reviewer request;
- **matching original PR already exists:** treat PR creation as idempotently complete and ensure the maintainer reviewer is requested.

For an advanced partial branch, the broker verifies the branch is exactly one commit above the requested base, the author/committer are the canonical bot identity, commit message matches, and the exact changed paths/blob SHAs match the original request. Any extra path, unexpected blob, history shape, source edit, missing/mismatched provenance, unexpected PR, or ambiguous state fails closed.

`main` may advance after the original partial transaction only when the original base is still an ancestor of current `main`; current issue scope and collision rules are always re-evaluated. Resume never deletes/recreates a claim or force-updates a branch.

### Ambiguous API results and bounded retry

Content-addressed Git blob creation may be retried once after a transient API error because recreating identical bytes is idempotent and the returned SHA must still exactly match the request. Non-force ref advancement handles an ambiguous API failure by re-reading the branch: it is accepted only if the branch already equals the exact intended commit; otherwise the original failure is propagated.

The broker does not blindly retry issue creation, milestone creation, PR creation, or arbitrary mutations whose prior success cannot be proven.

## Normal remote-agent flow

1. Read `AGENTS.md`, `.github/AGENTS.md`, the issue and its comments, current `main`, open PRs, and repository governance.
2. Confirm the issue is unclaimed and its owned paths do not collide with active PRs unless the documented reciprocal-coordination exception applies.
3. Prepare complete final contents for each changed file without creating a maintainer-authored branch or commit.
4. Use the connected GitHub API to create one immutable Git blob for each final file and retain each returned blob SHA.
5. Build the complete PR body using the repository template and the issue's declared scope.
6. Re-read the exact current `main` SHA immediately before command submission.
7. Encode the JSON request as the hidden base64url envelope and post one `/agent-commit-v1` command to the implementation issue with that `main` SHA and the blob references.
8. Watch **Agent GitHub App Command Broker**. A successful run creates the canonical branch/claim, commit, PR, and maintainer review request as `jasonbridges-agent[bot]`.
9. Verify the PR author and commit author/committer identity, requested reviewer, exact changed paths, and exact-head CI before review or merge.

The GitHub connection used by the remote agent does not become the authoring identity in this flow. Its job ends after staging blobs and submitting the owner-authorized command. During trusted preflight, the broker reads each bounded staged blob, verifies its canonical Git SHA, and materializes only the verified bytes into the private same-job request file (mode `0600`). After minting the short-lived App token, execution recreates those bytes as Git blobs under `jasonbridges-agent`, requires GitHub to return the exact requested SHA, revalidates repository state, and only then creates the canonical claim. Candidate bytes are never checked out, imported, executed, or logged while the App credential is present.

Do not retry an old failed command blindly. If validation failed before branch claim, refresh `main`, issue scope, open PR collisions, and blob state, then post a new command. If the branch was claimed, reconcile that claim first; do not overwrite or erase it to manufacture a retry.

## Validated end-to-end canary

The first completed production canary was issue #368 after the broker implementation merged in PR #367. The canary intentionally owned only `docs/security/agent-command-broker-canary.md` and made no production, authentication, SSO, secret, or workflow change.

Observed result:

- the **Agent GitHub App Command Broker** run completed successfully;
- canonical `work/issue-368` was created from the exact requested `main` parent;
- commit `88670d09aa2ea28fb0df1ac925ba83b18f68c156` was authored and committed by `jasonbridges-agent[bot]`;
- PR #369 was authored by `jasonbridges-agent[bot]` and requested `jasonbridges` as reviewer;
- only the canary-owned documentation path was changed;
- exact-head **Agent Coordination Validation** completed successfully; and
- PR #369 was closed without merge after verification, as intended for the inert canary.

This validates the core identity and coordination path: a remote agent can prepare immutable content without receiving the App credential, while the trusted default-branch workflow performs the claim, commit, and PR mutations under the canonical bot identity.

A future smoke test should use a newly created, narrowly scoped canary issue/path rather than reusing #368 or claiming a real implementation issue merely to test credentials.

## One-time bootstrap

The broker cannot bootstrap itself. The introducing PR is the one-time exception: it is created from the existing maintainer connector only when the repository owner explicitly authorizes that bootstrap. The issue and PR must record that attribution exception instead of representing the introducing commit as bot-authored.

After that PR is reviewed and merged, configure the repository with:

- Actions variable `AGENT_GITHUB_APP_ID`: the numeric App ID for `jasonbridges-agent`;
- Actions secret `AGENT_GITHUB_APP_PRIVATE_KEY`: the App private key PEM.

Never paste the private key into chat, an issue, a PR, a commit, logs, or an artifact. Use an owner-controlled workstation and `gh secret set ... < private-key.pem` (or the GitHub settings UI) so the value is transferred directly to GitHub secret storage.

A safe owner-side setup command is:

```bash
gh variable set AGENT_GITHUB_APP_ID --repo jasonbridges/homelab-infra --body '<numeric-app-id>'
gh secret set AGENT_GITHUB_APP_PRIVATE_KEY --repo jasonbridges/homelab-infra < /secure/path/to/jasonbridges-agent.private-key.pem
```

## Credential rotation

To rotate the GitHub App key:

1. Create a replacement private key for the existing `jasonbridges-agent` App from an owner-controlled GitHub session.
2. Replace `AGENT_GITHUB_APP_PRIVATE_KEY` in repository Actions secrets directly from the local PEM file.
3. Submit a harmless newly scoped broker canary or use the next real eligible issue and verify the App slug/PR actor is still `jasonbridges-agent[bot]`.
4. Revoke/delete the old App private key only after the replacement path is proven.

The installation token itself is intentionally not rotated or stored: `actions/create-github-app-token` mints it on demand and revokes it at job completion.

## Operational verification

For every broker-created PR, verify all of the following before review or merge:

- `work/issue-N` is the authoritative canonical claim and was created only once;
- claim comment actor is `jasonbridges-agent[bot]`;
- commit author/committer identity is the bot;
- PR author is the bot and `jasonbridges` is requested as reviewer;
- only issue-owned paths are changed, subject only to documented reciprocal coordination exceptions;
- applicable exact-head CI runs normally and required coordination/security gates pass; and
- no App private-key or installation-token value appears in logs or artifacts.

The successful #368 / #369 canary is the reference validation of this checklist, not a branch or issue to reuse.

## Failure and recovery

Treat failures differently depending on whether the canonical claim exists:

- **Before branch claim:** no implementation claim was acquired. Refresh `main`, issue state and comments, open PR path ownership, and staged blob state. Correct the request and submit a new owner comment. Do not edit and reuse the old command.
- **After branch claim:** the branch is intentionally preserved. If the claim has valid v2 provenance and matches one of the documented resumable states, submit a fresh `work.resume` command after refreshing repository state. Otherwise stop automatic retries and reconcile as owner/coordinator. Never force-update, delete, or recreate the claim merely to make the broker request pass.
- **Unexpected validation behavior:** fix the broker through a reviewed local-bot workflow/control-plane PR; do not weaken validation around a failing request.
- **Credential exposure suspicion:** revoke the affected App private key, rotate `AGENT_GITHUB_APP_PRIVATE_KEY`, inspect bot-authored activity, and prove the replacement path before revoking any remaining old key.

## Invariants

Broker use does not change the repository's GitHub Free/private-repository model or the one-interactive-login SSO invariant. It introduces a narrowly scoped machine identity for repository coordination and authoring; it does not add an end-user login path, broaden portal authentication, or require a reusable remote-agent GitHub credential.

## Removal

Permanent removal consists of a reviewed PR removing the broker workflow/script/tests/docs and updating `AGENTS.md`, followed by deletion of the two repository Actions configuration entries. The workstation bot path remains independent.
