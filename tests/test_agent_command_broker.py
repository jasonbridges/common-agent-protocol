from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import unittest
import unittest.mock
import zlib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "agent-command-broker.py"
SPEC = importlib.util.spec_from_file_location("agent_command_broker_target", SCRIPT)
assert SPEC and SPEC.loader
broker = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = broker
SPEC.loader.exec_module(broker)

TEST_CONTENT = b"broker-test-content"
TEST_SHA = hashlib.sha1(
    b"blob " + str(len(TEST_CONTENT)).encode() + b"\0" + TEST_CONTENT
).hexdigest()

ISSUE_BODY = """## Summary
X

## Scope ownership

Exclusive:
- `deploy/manifest.json`
- `tests/test_runner_keyring_quota.py`

Shared: none
"""
PR_BODY = """## Issue

Closes #362

## Claim

- Branch: `work/issue-362`

## Changed paths

- `deploy/manifest.json`

## Tests

ok

## Rollback

revert

## SSO impact

none

## Coordination

none
"""


def payload(**kw: Any) -> dict[str, Any]:
    p = {
        "version": 1,
        "issue": 362,
        "base_sha": "a" * 40,
        "commit_message": "fix(deploy): privileged validator (#362)",
        "files": [{"path": "deploy/manifest.json", "sha": TEST_SHA, "mode": "100644"}],
        "pr": {"title": "fix(deploy): privileged validator (#362)", "body": PR_BODY},
    }
    p.update(kw)
    return p


def event(p: dict[str, Any] | None = None, **comment_kw: Any) -> dict[str, Any]:
    body = broker.PREFIX + json.dumps(p or payload(), separators=(",", ":"))
    c = {
        "id": 7,
        "body": body,
        "user": {"login": "jasonbridges"},
        "author_association": "OWNER",
    }
    c.update(comment_kw)
    return {"issue": {"number": 362, "state": "open"}, "comment": c}


IMPLEMENTATION_BODY = """## Summary
implementation

## Acceptance criteria
- works

## Scope ownership
Exclusive:
- `deploy/manifest.json`
Shared: none

## Validation
- tests

## Rollback
revert

## SSO impact
none

## Coordination
none
"""


def v2_event(
    p: dict[str, Any],
    *,
    source_issue: int = 377,
    comment_id: int = 8,
    hidden: bool = True,
) -> dict[str, Any]:
    raw = json.dumps(p, separators=(",", ":")).encode()
    if hidden:
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        body = broker.PREFIX + broker.HIDDEN_PREFIX + encoded + broker.HIDDEN_SUFFIX
    else:
        body = broker.PREFIX + raw.decode()
    return {
        "issue": {"number": source_issue, "state": "open"},
        "comment": {
            "id": comment_id,
            "body": body,
            "user": {"login": "jasonbridges"},
            "author_association": "OWNER",
        },
    }


def work_update_payload(**kw: Any) -> dict[str, Any]:
    p = {
        "version": 2,
        "operation": "work.update",
        "issue": 362,
        "expected_head_sha": "f" * 40,
        "commit_message": "fix(deploy): follow-up (#362)",
        "files": [{"path": "deploy/manifest.json", "sha": TEST_SHA, "mode": "100644"}],
    }
    p.update(kw)
    return p


def inline_file(content: bytes, *, compress: bool = False, **kw: Any) -> dict[str, Any]:
    """Build a file entry carrying content inline instead of as a staged Git blob."""
    sha = hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\0" + content
    ).hexdigest()
    data = zlib.compress(content) if compress else content
    row = {
        "path": "deploy/manifest.json",
        "sha": sha,
        "mode": "100644",
        "inline": {
            "encoding": "zlib-base64" if compress else "base64",
            "data": base64.b64encode(data).decode(),
        },
    }
    row.update(kw)
    return row


MILESTONE = {"number": 1, "title": "Common Agent Protocol Hardening", "state": "open"}


class FakeGH:
    def __init__(self):
        self.branch = False
        self.branch_head: str | None = None
        self.issue_row = {
            "number": 362,
            "state": "open",
            "title": "implementation",
            "body": ISSUE_BODY,
            "milestone": dict(MILESTONE),
        }
        self.pr_milestone: int | None = None
        self.planning_row = {
            "number": 377,
            "state": "open",
            "title": "planning queue",
            "body": "## Summary\nqueue",
        }
        self.other_issues: dict[int, dict[str, Any]] = {}
        self.pulls: list[dict[str, Any]] = []
        self.pull_file_map: dict[int, set[str]] = {}
        self.posts: list[tuple[str, Any]] = []
        self.patches: list[tuple[str, Any]] = []
        self.milestones: list[dict[str, Any]] = [dict(MILESTONE)]
        self.comments: dict[int, dict[str, Any]] = {
            7: {
                "id": 7,
                "body": broker.PREFIX + json.dumps(payload(), separators=(",", ":")),
                "user": {"login": "jasonbridges"},
                "author_association": "OWNER",
            }
        }
        self.issue_comments: list[dict[str, Any]] = []
        self.comment_body = self.comments[7]["body"]

    def main_sha(self):
        return "a" * 40

    def branch_exists(self, _branch):
        return self.branch

    def branch_sha(self, _branch):
        return self.branch_head if self.branch else None

    def issue(self, n):
        if n == 362:
            return self.issue_row
        if n == 377:
            return self.planning_row
        return self.other_issues[n]

    def milestone(self, n):
        for row in self.milestones:
            if int(row["number"]) == n:
                return row
        raise AssertionError(f"missing milestone {n}")

    def pull_files(self, n):
        return self.pull_file_map[n]

    def pages(self, path):
        if path == "/pulls?state=open":
            yield from self.pulls
        elif path == "/milestones?state=open":
            yield from [row for row in self.milestones if row.get("state") == "open"]
        elif path == "/issues/362/comments":
            yield from self.issue_comments
        else:
            raise AssertionError(path)

    def get(self, path, allow_404=False):
        if path == "/git/blobs/" + TEST_SHA:
            return {
                "sha": TEST_SHA,
                "size": len(TEST_CONTENT),
                "encoding": "base64",
                "content": base64.b64encode(TEST_CONTENT).decode(),
            }
        if path.startswith("/issues/comments/"):
            comment_id = int(path.rsplit("/", 1)[1])
            if comment_id == 7:
                row = dict(self.comments[7])
                row["body"] = self.comment_body
                return row
            return self.comments[comment_id]
        if path.startswith("/git/commits/"):
            return {"tree": {"sha": "c" * 40}}
        if path.startswith("/compare/"):
            head = path.rsplit("...", 1)[1]
            return {
                "status": "ahead",
                "behind_by": 0,
                "ahead_by": 1,
                "commits": [
                    {
                        "sha": head,
                        "commit": {
                            "message": payload()["commit_message"],
                            "author": {
                                "name": broker.BOT_NAME,
                                "email": broker.BOT_EMAIL,
                            },
                            "committer": {
                                "name": broker.BOT_NAME,
                                "email": broker.BOT_EMAIL,
                            },
                        },
                    }
                ],
                "files": [
                    {
                        "filename": "deploy/manifest.json",
                        "sha": TEST_SHA,
                        "status": "modified",
                    }
                ],
            }
        if path == "/pulls/99/requested_reviewers":
            return {"users": [{"login": "jasonbridges"}]}
        raise AssertionError(path)

    def post(self, path, data):
        self.posts.append((path, data))
        if path == "/git/blobs":
            return {"sha": TEST_SHA}
        if path == "/git/refs":
            self.branch = True
            self.branch_head = data["sha"]
            return {"ref": "refs/heads/work/issue-362"}
        if path == "/git/trees":
            return {"sha": "d" * 40}
        if path == "/git/commits":
            return {"sha": "e" * 40}
        if path == "/pulls":
            row = {
                "number": 99,
                "html_url": "https://example/99",
                "title": data["title"],
                "body": data["body"],
                "head": {"ref": data["head"], "repo": {"full_name": broker.REPO}},
                "base": {"ref": data["base"]},
            }
            return row
        if path == "/milestones":
            row = {"number": 3, "title": data["title"], "state": "open"}
            self.milestones.append(row)
            return row
        if path == "/issues":
            return {
                "number": 400,
                "state": "open",
                "html_url": "https://example/issues/400",
                **data,
            }
        return {"ok": True}

    def patch(self, path, data):
        self.patches.append((path, data))
        if path.startswith("/git/refs/heads/"):
            self.branch = True
            self.branch_head = data["sha"]
            return {"object": {"sha": data["sha"]}}
        if path.startswith("/pulls/"):
            return {"number": int(path.rsplit("/", 1)[1]), **data}
        if path == "/issues/99":
            # PR #99 is a pull request; milestones are set on its issue record.
            self.pr_milestone = data["milestone"]
            return {"number": 99, "milestone": {"number": data["milestone"], "title": MILESTONE["title"]}}
        if path.startswith("/issues/"):
            target = int(path.rsplit("/", 1)[1])
            row = self.issue(target)
            row.update(data)
            if "milestone" in data:
                row["milestone"] = self.milestone(int(data["milestone"]))
            return row
        return {"ok": True}


class NoStagedBlobGH(FakeGH):
    """Inline content must never be fetched as a staged blob."""

    def get(self, path, allow_404=False):
        if path.startswith("/git/blobs/"):
            raise AssertionError("inline content must not be fetched as a staged blob")
        return super().get(path, allow_404)


class Tests(unittest.TestCase):
    def req(self, p=None, *, hidden=False):
        e = event(p)
        if hidden:
            raw = json.dumps(p or payload(), separators=(",", ":")).encode()
            encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
            e["comment"]["body"] = (
                broker.PREFIX + broker.HIDDEN_PREFIX + encoded + broker.HIDDEN_SUFFIX
            )
        return broker.from_event(e)

    def test_owner_command_parses(self):
        r = self.req()
        self.assertEqual(r.issue, 362)
        self.assertEqual(r.branch, "work/issue-362")

    def test_hidden_owner_command_parses(self):
        self.assertEqual(self.req(hidden=True).issue, 362)

    def test_hidden_html_terminator_stays_encoded(self):
        p = payload()
        p["pr"] = dict(p["pr"])
        p["pr"]["body"] += "\nterminator --> remains data"
        r = self.req(p, hidden=True)
        self.assertIn("-->", r.body)

    def test_hidden_malformed_rejected(self):
        e = event()
        e["comment"]["body"] = (
            broker.PREFIX + broker.HIDDEN_PREFIX + "%%%" + broker.HIDDEN_SUFFIX
        )
        self.assertRaises(broker.BrokerError, broker.from_event, e)

    def test_pr_comment_and_non_owner_rejected(self):
        e = event()
        e["issue"]["pull_request"] = {}
        self.assertRaises(broker.BrokerError, broker.from_event, e)
        self.assertRaises(
            broker.BrokerError, broker.from_event, event(user={"login": "x"})
        )

    def test_malformed_oversize_and_unknown_fields_rejected(self):
        e = event()
        e["comment"]["body"] = broker.PREFIX + "{"
        self.assertRaises(broker.BrokerError, broker.from_event, e)
        e = event()
        e["comment"]["body"] = broker.PREFIX + ("x" * broker.MAX_COMMENT)
        self.assertRaises(broker.BrokerError, broker.from_event, e)
        self.assertRaises(broker.BrokerError, self.req, payload(extra=True))

    def test_workflow_scope_escape_and_mode_rejected(self):
        self.assertRaises(
            broker.BrokerError,
            self.req,
            payload(files=[{"path": ".github/workflows/x.yml", "sha": TEST_SHA}]),
        )
        self.assertRaises(
            broker.BrokerError,
            self.req,
            payload(
                files=[
                    {"path": "deploy/manifest.json", "sha": TEST_SHA, "mode": "120000"}
                ]
            ),
        )
        r = self.req(payload(files=[{"path": "README.md", "sha": TEST_SHA}]))
        self.assertRaises(broker.BrokerError, broker.validate_remote, FakeGH(), r)

    def test_stale_base_and_existing_claim_rejected(self):
        r = self.req()
        g = FakeGH()
        r2 = broker.Request(
            r.issue,
            "f" * 40,
            r.message,
            r.files,
            r.title,
            r.body,
            r.comment_id,
            r.comment_digest,
        )
        self.assertRaises(broker.BrokerError, broker.validate_remote, g, r2)
        g.branch = True
        self.assertRaises(broker.BrokerError, broker.validate_remote, g, r)

    def test_github_line_wrapped_blob_base64_is_accepted(self):
        class G(FakeGH):
            def get(self, path, allow_404=False):
                if path == "/git/blobs/" + TEST_SHA:
                    encoded = base64.b64encode(TEST_CONTENT).decode()
                    wrapped = "\n".join(
                        encoded[i : i + 4] for i in range(0, len(encoded), 4)
                    )
                    return {
                        "sha": TEST_SHA,
                        "size": len(TEST_CONTENT),
                        "encoding": "base64",
                        "content": wrapped,
                    }
                return super().get(path, allow_404)

        materialized = broker.materialize_blobs(G(), self.req())
        self.assertEqual(
            base64.b64decode(materialized["deploy/manifest.json"]["content_b64"]),
            TEST_CONTENT,
        )

    def test_github_blob_base64_rejects_non_whitespace_garbage(self):
        class G(FakeGH):
            def get(self, path, allow_404=False):
                if path == "/git/blobs/" + TEST_SHA:
                    encoded = base64.b64encode(TEST_CONTENT).decode()
                    return {
                        "sha": TEST_SHA,
                        "size": len(TEST_CONTENT),
                        "encoding": "base64",
                        "content": encoded[:4] + "%" + encoded[4:],
                    }
                return super().get(path, allow_404)

        self.assertRaises(broker.BrokerError, broker.materialize_blobs, G(), self.req())

    def test_missing_or_large_blob_rejected(self):
        class G(FakeGH):
            def get(self, path, allow_404=False):
                if path.startswith("/git/blobs/"):
                    return {"sha": TEST_SHA, "size": broker.MAX_BLOB + 1}
                return super().get(path, allow_404)

        self.assertRaises(broker.BrokerError, broker.validate_remote, G(), self.req())

    def test_invalid_pr_metadata_rejected(self):
        r = self.req(payload(pr={"title": "x", "body": "## Issue\nCloses #362"}))
        self.assertRaises(broker.BrokerError, broker.validate_remote, FakeGH(), r)

    def test_exact_collision_rejected(self):
        g = FakeGH()
        g.pulls = [{"number": 10, "head": {"ref": "work/issue-10"}}]
        g.pull_file_map[10] = {"deploy/manifest.json"}
        g.other_issues[10] = {
            "state": "open",
            "body": "## Scope ownership\nExclusive:\n- `other.txt`\nShared: none",
        }
        self.assertRaises(broker.BrokerError, broker.validate_remote, g, self.req())

    def test_exclusive_collision_rejected(self):
        g = FakeGH()
        g.pulls = [{"number": 10, "head": {"ref": "work/issue-10"}}]
        g.pull_file_map[10] = {"other.txt"}
        g.other_issues[10] = {
            "state": "open",
            "body": "## Scope ownership\nExclusive:\n- `deploy/**`\nShared: none",
        }
        self.assertRaises(broker.BrokerError, broker.validate_remote, g, self.req())

    def test_reciprocal_exception_allows_collision(self):
        g = FakeGH()
        g.pulls = [{"number": 10, "head": {"ref": "work/issue-10"}}]
        g.pull_file_map[10] = {"deploy/manifest.json"}
        g.issue_row["body"] = ISSUE_BODY + "\nCoordination-Exception: #10\n"
        g.other_issues[10] = {
            "state": "open",
            "body": "## Scope ownership\nExclusive:\n- `deploy/**`\nShared: none\nCoordination-Exception: #362\n",
        }
        broker.validate_remote(g, self.req())

    def test_edited_source_comment_rejected(self):
        r = self.req()
        g = FakeGH()
        g.comment_body += "x"
        self.assertRaises(broker.BrokerError, broker.verify_comment, g, r)

    def test_successful_mutation_is_issue_scoped(self):
        r = self.req()
        g = FakeGH()
        materialized = broker.materialize_blobs(g, r)
        n, url = broker.mutate(g, r, materialized)
        self.assertEqual((n, url), (99, "https://example/99"))
        self.assertTrue(g.branch)
        self.assertEqual(g.patches[0][0], "/git/refs/heads/work/issue-362")
        pr_payload = next(data for path, data in g.posts if path == "/pulls")
        self.assertEqual(pr_payload["base"], "main")
        self.assertEqual(pr_payload["head"], "work/issue-362")
        self.assertFalse(any(path == "/merges" for path, _ in g.posts))

    def test_app_execution_recreates_preflight_verified_blob(self):
        r = self.req()
        preflight = FakeGH()
        materialized = broker.materialize_blobs(preflight, r)

        class AppGH(FakeGH):
            def get(self, path, allow_404=False):
                if path.startswith("/git/blobs/"):
                    raise AssertionError("App must not GET staged dangling blob")
                return super().get(path, allow_404)

        g = AppGH()
        broker.mutate(g, r, materialized)
        self.assertTrue(any(path == "/git/blobs" for path, _ in g.posts))

    def test_saved_request_round_trip(self):
        r = self.req()
        restored = broker.request_from_saved(dict(r.json()))
        self.assertEqual(restored, r)

    def v2(self, p, *, source_issue=377, comment_id=8, gh=None):
        e = v2_event(p, source_issue=source_issue, comment_id=comment_id)
        cmd = broker.from_event(e)
        if gh is not None:
            gh.comments[comment_id] = dict(e["comment"])
        return cmd

    def canonical_pr(self, *, head="f" * 40):
        return {
            "number": 99,
            "html_url": "https://example/99",
            "title": "fix(deploy): privileged validator (#362)",
            "body": PR_BODY,
            "head": {
                "ref": "work/issue-362",
                "sha": head,
                "repo": {"full_name": broker.REPO},
            },
            "base": {"ref": "main"},
            "milestone": dict(MILESTONE),
        }

    def test_v2_rejects_unknown_operations_fields_and_wrong_planning_source(self):
        self.assertRaises(
            broker.BrokerError,
            broker.from_event,
            v2_event({"version": 2, "operation": "repo.delete"}),
        )
        p = {
            "version": 2,
            "operation": "plan.create_milestone",
            "title": "x",
            "admin": True,
        }
        self.assertRaises(broker.BrokerError, broker.from_event, v2_event(p))
        p.pop("admin")
        self.assertRaises(
            broker.BrokerError, broker.from_event, v2_event(p, source_issue=362)
        )

    def test_plan_create_milestone_and_duplicate_rejection(self):
        g = FakeGH()
        cmd = self.v2(
            {"version": 2, "operation": "plan.create_milestone", "title": "Broker v2"},
            gh=g,
        )
        broker.validate_planning(g, cmd)
        result = broker.mutate_planning(g, cmd)
        self.assertIn("milestone #3", result)
        cmd2 = self.v2(
            {"version": 2, "operation": "plan.create_milestone", "title": "Broker v2"},
            comment_id=9,
            gh=g,
        )
        self.assertRaises(broker.BrokerError, broker.validate_planning, g, cmd2)

    def test_plan_create_issue_requires_canonical_implementation_body(self):
        g = FakeGH()
        p = {
            "version": 2,
            "operation": "plan.create_issue",
            "title": "feat: implementation",
            "body": IMPLEMENTATION_BODY,
            "implementation": True,
        }
        cmd = self.v2(p, gh=g)
        broker.validate_planning(g, cmd)
        result = broker.mutate_planning(g, cmd)
        self.assertEqual(result, "issue #400")
        bad = dict(p, body="## Summary\nmissing contracts")
        bad_cmd = self.v2(bad, comment_id=9, gh=g)
        self.assertRaises(broker.BrokerError, broker.validate_planning, g, bad_cmd)

    def test_plan_create_issue_and_assign_existing_open_milestone(self):
        g = FakeGH()
        g.milestones.append({"number": 5, "title": "M", "state": "open"})
        p = {
            "version": 2,
            "operation": "plan.create_issue",
            "title": "tracking",
            "body": "## Summary\ntracking only",
            "implementation": False,
            "milestone": 5,
        }
        cmd = self.v2(p, gh=g)
        broker.validate_planning(g, cmd)
        broker.mutate_planning(g, cmd)
        g.other_issues[401] = {
            "number": 401,
            "state": "open",
            "title": "x",
            "body": "body",
        }
        assign = self.v2(
            {
                "version": 2,
                "operation": "plan.assign_milestone",
                "target_issue": 401,
                "milestone": 5,
            },
            comment_id=9,
            gh=g,
        )
        broker.mutate_planning(g, assign)
        self.assertEqual(g.other_issues[401]["milestone"]["number"], 5)

    def test_plan_update_issue_uses_optimistic_body_and_title_concurrency(self):
        g = FakeGH()
        g.other_issues[401] = {
            "number": 401,
            "state": "open",
            "title": "old",
            "body": IMPLEMENTATION_BODY,
        }
        p = {
            "version": 2,
            "operation": "plan.update_issue",
            "target_issue": 401,
            "expected_body_sha256": broker._body_digest(IMPLEMENTATION_BODY),
            "expected_title": "old",
            "title": "new",
            "body": IMPLEMENTATION_BODY.replace(
                "implementation", "implementation updated", 1
            ),
        }
        cmd = self.v2(p, gh=g)
        broker.mutate_planning(g, cmd)
        self.assertEqual(g.other_issues[401]["title"], "new")
        stale = dict(p, expected_body_sha256="0" * 64)
        stale_cmd = self.v2(stale, comment_id=9, gh=g)
        self.assertRaises(broker.BrokerError, broker.validate_planning, g, stale_cmd)

    def test_work_update_requires_exact_head_and_excludes_own_pr_collision(self):
        g = FakeGH()
        g.branch = True
        g.branch_head = "f" * 40
        g.pulls = [self.canonical_pr()]
        g.pull_file_map[99] = {"deploy/manifest.json"}
        cmd = self.v2(work_update_payload(), source_issue=362, gh=g)
        _, pr, files = broker.validate_work_update(g, cmd)
        self.assertEqual(pr["number"], 99)
        materialized = broker.materialize_file_set(g, files)
        sha, number = broker.mutate_work_update(g, cmd, materialized)
        self.assertEqual(number, 99)
        self.assertEqual(sha, "e" * 40)
        self.assertEqual(g.branch_head, "e" * 40)
        stale = self.v2(
            work_update_payload(expected_head_sha="1" * 40),
            source_issue=362,
            comment_id=9,
            gh=g,
        )
        self.assertRaises(broker.BrokerError, broker.validate_work_update, g, stale)

    def test_work_update_rejects_foreign_collision_and_workflow_path(self):
        g = FakeGH()
        g.branch = True
        g.branch_head = "f" * 40
        g.pulls = [
            self.canonical_pr(),
            {"number": 10, "head": {"ref": "work/issue-10"}, "base": {"ref": "main"}},
        ]
        g.pull_file_map[99] = {"deploy/manifest.json"}
        g.pull_file_map[10] = {"deploy/manifest.json"}
        g.other_issues[10] = {
            "number": 10,
            "state": "open",
            "body": "## Scope ownership\nExclusive:\n- `other.txt`\nShared: none",
        }
        cmd = self.v2(work_update_payload(), source_issue=362, gh=g)
        self.assertRaises(broker.BrokerError, broker.validate_work_update, g, cmd)
        bad = work_update_payload(
            files=[{"path": ".github/workflows/x.yml", "sha": TEST_SHA}]
        )
        self.assertRaises(
            broker.BrokerError, broker.from_event, v2_event(bad, source_issue=362)
        )

    def test_work_update_can_update_only_validated_pr_title_body(self):
        g = FakeGH()
        g.branch = True
        g.branch_head = "f" * 40
        g.pulls = [self.canonical_pr()]
        g.pull_file_map[99] = {"deploy/manifest.json"}
        new_body = PR_BODY + "\nextra detail\n"
        cmd = self.v2(
            work_update_payload(
                pr={"title": "fix(deploy): revised (#362)", "body": new_body}
            ),
            source_issue=362,
            gh=g,
        )
        materialized = broker.materialize_file_set(g, broker._files_for_v2(cmd))
        broker.mutate_work_update(g, cmd, materialized)
        self.assertTrue(any(path == "/pulls/99" for path, _ in g.patches))
        self.assertFalse(any(path == "/merges" for path, _ in g.posts))

    def _resume_fixture(self, *, head=None, with_pr=False):
        g = FakeGH()
        req = self.req()
        g.branch = True
        g.branch_head = head or req.base_sha
        g.issue_comments = [
            {
                "user": {"login": broker.BOT_NAME},
                "body": broker._claim_body(req),
            }
        ]
        if with_pr:
            row = self.canonical_pr(head=g.branch_head)
            row["title"] = req.title
            row["body"] = req.body
            g.pulls = [row]
            g.pull_file_map[99] = {"deploy/manifest.json"}
        p = {
            "version": 2,
            "operation": "work.resume",
            "issue": 362,
            "expected_head_sha": g.branch_head,
            "original_comment_id": 7,
            "original_comment_sha256": broker._body_digest(g.comment_body),
            "request_sha256": broker.request_sha256(req),
        }
        cmd = self.v2(p, source_issue=362, gh=g)
        return g, req, cmd

    def test_resume_branch_at_base_reconstructs_and_opens_pr(self):
        g, req, cmd = self._resume_fixture()
        original, state, _ = broker.validate_resume(g, cmd)
        self.assertEqual((original, state), (req, "at-base"))
        materialized = broker.materialize_blobs(g, req)
        number, _ = broker.mutate_resume(g, cmd, materialized)
        self.assertEqual(number, 99)
        self.assertEqual(g.branch_head, "e" * 40)

    def test_resume_commit_only_opens_pr_without_rewriting_branch(self):
        g, req, cmd = self._resume_fixture(head="e" * 40)
        original, state, _ = broker.validate_resume(g, cmd)
        self.assertEqual((original, state), (req, "commit-only"))
        number, _ = broker.mutate_resume(g, cmd, {})
        self.assertEqual(number, 99)
        ref_patches = [row for row in g.patches if row[0].startswith("/git/refs/")]
        self.assertEqual(ref_patches, [])

    def test_resume_matching_existing_pr_is_idempotent(self):
        g, _, cmd = self._resume_fixture(head="e" * 40, with_pr=True)
        _, state, _ = broker.validate_resume(g, cmd)
        self.assertEqual(state, "pr-exists")
        before = len([row for row in g.posts if row[0] == "/pulls"])
        number, _ = broker.mutate_resume(g, cmd, {})
        after = len([row for row in g.posts if row[0] == "/pulls"])
        self.assertEqual((number, before, after), (99, 0, 0))

    def test_resume_rejects_missing_provenance_and_unexpected_advance(self):
        g, _, cmd = self._resume_fixture()
        g.issue_comments = []
        self.assertRaises(broker.BrokerError, broker.validate_resume, g, cmd)
        g, _, cmd = self._resume_fixture(head="e" * 40)

        class DriftGH(FakeGH):
            pass

        original_get = g.get

        def bad_get(path, allow_404=False):
            row = original_get(path, allow_404)
            if path.startswith("/compare/"):
                row = dict(row)
                row["ahead_by"] = 2
            return row

        g.get = bad_get
        self.assertRaises(broker.BrokerError, broker.validate_resume, g, cmd)

    def test_saved_v2_command_round_trip_and_source_edit_detection(self):
        g = FakeGH()
        cmd = self.v2(
            {"version": 2, "operation": "plan.create_milestone", "title": "x"}, gh=g
        )
        saved = broker._saved_command(cmd, {"materialized_blobs": {}})
        restored, materialized = broker._command_from_saved(saved)
        self.assertEqual(restored, cmd)
        self.assertEqual(materialized, {})
        g.comments[8]["body"] += "edited"
        self.assertRaises(broker.BrokerError, broker.verify_comment, g, cmd)

    def test_materialized_blob_tamper_fails_closed(self):
        r = self.req()
        g = FakeGH()
        materialized = broker.materialize_blobs(g, r)
        materialized["deploy/manifest.json"]["content_b64"] = base64.b64encode(
            b"tampered"
        ).decode()
        self.assertRaises(broker.BrokerError, broker.recreate_blobs, g, r, materialized)

    def test_ref_advance_treats_ambiguous_failure_as_success_only_if_head_matches(self):
        g = FakeGH()
        g.branch = True
        g.branch_head = "a" * 40
        original_patch = g.patch

        def ambiguous(path, data):
            if path.startswith("/git/refs/"):
                g.branch_head = data["sha"]
                raise broker.BrokerError("simulated 500 after write")
            return original_patch(path, data)

        g.patch = ambiguous
        broker._advance_ref_idempotent(g, "work/issue-362", "e" * 40)
        self.assertEqual(g.branch_head, "e" * 40)

    def test_planning_cannot_disguise_or_strip_implementation_scope(self):
        g = FakeGH()
        disguised = {
            "version": 2,
            "operation": "plan.create_issue",
            "title": "bad",
            "body": "## Summary\nx\n\n## Scope ownership\nExclusive:\nShared: none",
            "implementation": False,
        }
        cmd = self.v2(disguised, gh=g)
        self.assertRaises(broker.BrokerError, broker.validate_planning, g, cmd)
        g.other_issues[401] = {
            "number": 401,
            "state": "open",
            "title": "impl",
            "body": IMPLEMENTATION_BODY,
        }
        strip = {
            "version": 2,
            "operation": "plan.update_issue",
            "target_issue": 401,
            "expected_body_sha256": broker._body_digest(IMPLEMENTATION_BODY),
            "body": "## Summary\nremoved scope",
        }
        strip_cmd = self.v2(strip, comment_id=9, gh=g)
        self.assertRaises(broker.BrokerError, broker.validate_planning, g, strip_cmd)

    def test_planning_rejects_closed_issue_and_milestone_resources(self):
        g = FakeGH()
        g.other_issues[401] = {
            "number": 401,
            "state": "closed",
            "title": "x",
            "body": "body",
        }
        g.milestones.append({"number": 5, "title": "closed", "state": "closed"})
        assign = self.v2(
            {
                "version": 2,
                "operation": "plan.assign_milestone",
                "target_issue": 401,
                "milestone": 5,
            },
            gh=g,
        )
        self.assertRaises(broker.BrokerError, broker.validate_planning, g, assign)

    def test_work_update_rejects_foreign_repository_pr(self):
        g = FakeGH()
        g.branch = True
        g.branch_head = "f" * 40
        pr = self.canonical_pr()
        pr["head"]["repo"]["full_name"] = "someone/fork"
        g.pulls = [pr]
        g.pull_file_map[99] = {"deploy/manifest.json"}
        cmd = self.v2(work_update_payload(), source_issue=362, gh=g)
        self.assertRaises(broker.BrokerError, broker.validate_work_update, g, cmd)

    def test_resume_revalidates_new_collision_after_original_failure(self):
        g, _, cmd = self._resume_fixture()
        g.pulls = [
            {"number": 10, "head": {"ref": "work/issue-10"}, "base": {"ref": "main"}}
        ]
        g.pull_file_map[10] = {"deploy/manifest.json"}
        g.other_issues[10] = {
            "number": 10,
            "state": "open",
            "body": "## Scope ownership\nExclusive:\n- `other.txt`\nShared: none",
        }
        self.assertRaises(broker.BrokerError, broker.validate_resume, g, cmd)

    def test_resume_allows_main_fast_forward_only_when_original_base_remains_ancestor(
        self,
    ):
        g, req, cmd = self._resume_fixture()
        g.main_sha = lambda: "9" * 40
        original_get = g.get

        def ancestor_get(path, allow_404=False):
            if path == f"/compare/{req.base_sha}...{'9' * 40}":
                return {
                    "status": "ahead",
                    "behind_by": 0,
                    "ahead_by": 2,
                    "commits": [],
                    "files": [],
                }
            return original_get(path, allow_404)

        g.get = ancestor_get
        _, state, _ = broker.validate_resume(g, cmd)
        self.assertEqual(state, "at-base")

        def divergent_get(path, allow_404=False):
            if path == f"/compare/{req.base_sha}...{'9' * 40}":
                return {"status": "diverged", "behind_by": 1, "ahead_by": 2}
            return original_get(path, allow_404)

        g.get = divergent_get
        self.assertRaises(broker.BrokerError, broker.validate_resume, g, cmd)

    def test_resume_rejects_original_source_comment_digest_mismatch(self):
        g, _, cmd = self._resume_fixture()
        g.comment_body += "edited"
        self.assertRaises(broker.BrokerError, broker.validate_resume, g, cmd)

    def test_unmilestoned_or_closed_milestone_issue_is_refused_before_claim(self):
        for milestone in (None, {"number": 1, "title": "old", "state": "closed"}):
            with self.subTest(milestone=milestone):
                g = FakeGH()
                g.issue_row["milestone"] = milestone
                r = self.req()
                self.assertRaisesRegex(
                    broker.BrokerError, "no open milestone", broker.validate_remote, g, r
                )
                self.assertRaisesRegex(
                    broker.BrokerError, "no open milestone", broker.mutate, g, r, {}
                )
                self.assertEqual(g.posts, [])
                self.assertFalse(g.branch)

    def test_initial_pr_receives_issue_milestone_and_reports_it(self):
        g = FakeGH()
        r = self.req()
        broker.mutate(g, r, broker.materialize_blobs(g, r))
        self.assertEqual(g.pr_milestone, MILESTONE["number"])
        success = [
            data["body"] for path, data in g.posts if path == "/issues/362/comments"
        ][-1]
        self.assertIn(f"- Milestone: #{MILESTONE['number']}", success)

    def test_initial_pr_fails_closed_when_milestone_cannot_be_verified(self):
        g = FakeGH()
        original_patch = g.patch

        def ignore_milestone(path, data):
            if path == "/issues/99":
                return {"number": 99, "milestone": None}
            return original_patch(path, data)

        g.patch = ignore_milestone
        r = self.req()
        self.assertRaisesRegex(
            broker.BrokerError,
            "milestone parity",
            broker.mutate,
            g,
            r,
            broker.materialize_blobs(g, r),
        )
        failure = [
            data["body"] for path, data in g.posts if path == "/issues/362/comments"
        ][-1]
        self.assertTrue(failure.startswith("BOT BROKER FAILURE"))

    def test_work_update_restores_milestone_parity_only_when_needed(self):
        for current, expect_patch in (
            (None, True),
            ({"number": 7, "state": "open"}, True),
            (dict(MILESTONE), False),
        ):
            with self.subTest(current=current):
                g = FakeGH()
                g.branch = True
                g.branch_head = "f" * 40
                pr = self.canonical_pr()
                pr["milestone"] = current
                g.pulls = [pr]
                g.pull_file_map[99] = {"deploy/manifest.json"}
                cmd = self.v2(work_update_payload(), source_issue=362, gh=g)
                files = broker._files_for_v2(cmd)
                broker.mutate_work_update(g, cmd, broker.materialize_file_set(g, files))
                patched = any(path == "/issues/99" for path, _ in g.patches)
                self.assertEqual(patched, expect_patch)
                if expect_patch:
                    self.assertEqual(g.pr_milestone, MILESTONE["number"])

    def test_resume_created_pr_receives_issue_milestone(self):
        g, req, cmd = self._resume_fixture()
        broker.mutate_resume(g, cmd, broker.materialize_blobs(g, req))
        self.assertEqual(g.pr_milestone, MILESTONE["number"])

    def _hidden_event(self, p):
        e = event(p)
        raw = json.dumps(p, separators=(",", ":")).encode()
        encoded = base64.urlsafe_b64encode(raw).decode().rstrip("=")
        e["comment"]["body"] = (
            broker.PREFIX + broker.HIDDEN_PREFIX + encoded + broker.HIDDEN_SUFFIX
        )
        return e

    def test_hidden_envelope_accepts_only_one_allowlisted_attribution_footer(self):
        e = self._hidden_event(payload())
        body = e["comment"]["body"]
        session_footer = (
            "\n\n---\n_Generated by [Claude Code]"
            "(https://claude.ai/code/session_01FxRrsrzabsWpNzm2w3tKxR)_"
        )
        for suffix in (
            broker.ATTRIBUTION_FOOTER,
            broker.ATTRIBUTION_FOOTER + "\n",
            session_footer,
            session_footer + "\n",
        ):
            with self.subTest(accepted=suffix):
                e["comment"]["body"] = body + suffix
                req = broker.from_event(e)
                self.assertEqual(req.issue, 362)
                self.assertEqual(
                    req.comment_digest,
                    hashlib.sha256((body + suffix).encode()).hexdigest(),
                )
        for suffix in (
            broker.ATTRIBUTION_FOOTER + "x",
            broker.ATTRIBUTION_FOOTER + "\n\n",
            broker.ATTRIBUTION_FOOTER + broker.ATTRIBUTION_FOOTER,
            "\nextra",
            "\n\n---\n_Generated by [Claude Code](https://attacker.example)_",
        ):
            with self.subTest(rejected=suffix):
                e["comment"]["body"] = body + suffix
                self.assertRaises(broker.BrokerError, broker.from_event, e)

    def test_raw_json_command_does_not_accept_attribution_footer(self):
        e = event()
        e["comment"]["body"] += broker.ATTRIBUTION_FOOTER
        self.assertRaises(broker.BrokerError, broker.from_event, e)

    def test_inline_content_replaces_staged_blob_without_changing_request_identity(self):
        staged = self.req()
        for compress in (False, True):
            with self.subTest(compress=compress):
                e = event(payload(files=[inline_file(TEST_CONTENT, compress=compress)]))
                inline = broker.from_event(e)
                self.assertEqual(inline.files, staged.files)
                self.assertEqual(inline.files[0].inline, TEST_CONTENT)
                self.assertEqual(
                    broker.request_sha256(inline), broker.request_sha256(staged)
                )
                g = NoStagedBlobGH()
                g.comment_body = e["comment"]["body"]
                materialized = broker.materialize_blobs(g, inline)
                self.assertEqual(
                    base64.b64decode(
                        materialized["deploy/manifest.json"]["content_b64"]
                    ),
                    TEST_CONTENT,
                )
                number, _ = broker.mutate(g, inline, materialized)
                self.assertEqual(number, 99)

    def test_work_update_accepts_inline_zlib_content(self):
        g = NoStagedBlobGH()
        g.branch = True
        g.branch_head = "f" * 40
        g.pulls = [self.canonical_pr()]
        g.pull_file_map[99] = {"deploy/manifest.json"}
        cmd = self.v2(
            work_update_payload(files=[inline_file(TEST_CONTENT, compress=True)]),
            source_issue=362,
            gh=g,
        )
        files = broker._files_for_v2(cmd)
        sha, number = broker.mutate_work_update(
            g, cmd, broker.materialize_file_set(g, files)
        )
        self.assertEqual((sha, number), ("e" * 40, 99))

    def test_inline_content_integrity_and_bounds_fail_closed(self):
        def encoded(data: bytes) -> str:
            return base64.b64encode(data).decode()

        compressed = zlib.compress(TEST_CONTENT)
        cases = (
            (
                inline_file(b"other", sha=TEST_SHA),
                "integrity failure",
            ),
            (
                inline_file(
                    TEST_CONTENT,
                    inline={"encoding": "base64", "data": "%%%"},
                ),
                "Malformed",
            ),
            (
                inline_file(
                    TEST_CONTENT,
                    inline={"encoding": "gzip", "data": "AA=="},
                ),
                "Invalid",
            ),
            (inline_file(TEST_CONTENT, sha=None), "cannot carry inline content"),
            (
                inline_file(
                    TEST_CONTENT,
                    inline={
                        "encoding": "zlib-base64",
                        "data": encoded(compressed[:-3]),
                    },
                ),
                "Malformed",
            ),
        )
        for row, message in cases:
            with self.subTest(message=message):
                self.assertRaisesRegex(
                    broker.BrokerError, message, self.req, payload(files=[row])
                )
        oversized = {
            "encoding": "base64",
            "data": encoded(b"\0" * (broker.MAX_BLOB + 1)),
        }
        self.assertRaisesRegex(
            broker.BrokerError,
            "oversized",
            broker._inline_content,
            oversized,
            "x",
            TEST_SHA,
        )

    def test_scope_accepts_heading_forms_and_stops_at_other_headings(self):
        body = (
            "## Scope ownership\n\n### Exclusive\n\n- `a/**`\n- `b.py`\n\n"
            "### Shared\n\n- `c.md`\n\n### Notes\n\n- `not/scope.txt`\n\n"
            "## Validation\n\n- `ignored/**`\n"
        )
        self.assertEqual(broker.scope(body), ({"a/**", "b.py"}, {"c.md"}))
        level_two = (
            "## Scope ownership\n\n## Exclusive\n\n- `a/**`\n\n"
            "## Shared\n\n- none\n\n## Validation\n\n- `x/**`\n"
        )
        self.assertEqual(broker.scope(level_two), ({"a/**"}, set()))

    def test_heading_form_exclusive_scope_participates_in_collision_detection(self):
        g = FakeGH()
        g.pulls = [
            {
                "number": 10,
                "head": {"ref": "work/issue-10"},
                "base": {"ref": "main"},
            }
        ]
        g.pull_file_map[10] = {"other.txt"}
        g.other_issues[10] = {
            "number": 10,
            "state": "open",
            "body": (
                "## Scope ownership\n\n### Exclusive\n\n- `deploy/**`\n\n"
                "### Shared\n\n- none\n"
            ),
        }
        self.assertRaisesRegex(
            broker.BrokerError,
            "Path collision with PR #10",
            broker.validate_remote,
            g,
            self.req(),
        )

    def test_workflow_concurrency_is_job_scoped_and_preserves_command_groups(self):
        wf_path = ROOT / ".github/workflows/agent-command-broker.yml"
        if not wf_path.exists():
            wf_path = ROOT / "templates/workflows/agent-command-broker.yml"
        workflow = wf_path.read_text()
        self.assertNotRegex(workflow, r"(?m)^concurrency:")
        broker_job = workflow.split("  broker:\n", 1)[1]
        self.assertIn("    concurrency:\n", broker_job)
        self.assertIn("vars.AGENT_BROKER_PLANNING_ISSUE", broker_job)
        self.assertIn("format('planning-{0}', github.event.comment.id)", broker_job)
        self.assertIn("format('issue-{0}', github.event.issue.number)", broker_job)
        self.assertIn("cancel-in-progress: false", broker_job)

        def concurrency_key(issue: int, comment: int) -> str:
            suffix = f"planning-{comment}" if issue == 377 else f"issue-{issue}"
            return "agent-command-broker-" + suffix

        self.assertNotEqual(concurrency_key(377, 100), concurrency_key(377, 101))
        self.assertEqual(concurrency_key(388, 100), concurrency_key(388, 101))

    def test_workflow_unauthorized_comments_cannot_enter_job_concurrency(self):
        wf_path = ROOT / ".github/workflows/agent-command-broker.yml"
        if not wf_path.exists():
            wf_path = ROOT / "templates/workflows/agent-command-broker.yml"
        workflow = wf_path.read_text()
        broker_job = workflow.split("  broker:\n", 1)[1]
        auth_end = broker_job.index("    concurrency:\n")
        authorization = broker_job[:auth_end]
        self.assertIn(
            "github.event.comment.user.login == (vars.AGENT_BROKER_OWNER || github.repository_owner)",
            authorization,
        )
        self.assertIn(
            "github.event.comment.author_association == 'OWNER'", authorization
        )
        self.assertIn(
            "startsWith(github.event.comment.body, '/agent-commit-v1')", authorization
        )
        self.assertIn(
            "fail the job-level `if` before they can enter an authorized group",
            workflow,
        )

        def authorized(login: str, association: str, body: str) -> bool:
            return (
                login == "jasonbridges"
                and association == "OWNER"
                and body.startswith(broker.PREFIX.strip())
            )

        self.assertTrue(authorized("jasonbridges", "OWNER", broker.PREFIX + "{}"))
        self.assertFalse(authorized(broker.BOT_NAME, "NONE", "BOT BROKER SUCCESS"))
        self.assertFalse(authorized("jasonbridges", "OWNER", "ordinary discussion"))

    def test_configuration_template_empty_and_whitespace_env_fallbacks(self):
        empty_env = {
            "AGENT_BROKER_OWNER": "jasonbridges",
            "AGENT_BOT_NAME": "",
            "AGENT_BOT_EMAIL": "",
            "AGENT_BROKER_BRANCH_PATTERN": "",
            "AGENT_BROKER_BRANCH_RE": "",
            "AGENT_BROKER_PLANNING_ISSUE": "",
        }
        with unittest.mock.patch.dict(broker.os.environ, empty_env, clear=False):
            self.assertEqual(broker.get_owner(), "jasonbridges")
            self.assertEqual(broker.get_bot_name(), "jasonbridges-agent[bot]")
            self.assertEqual(
                broker.get_bot_email(),
                "331491158+jasonbridges-agent[bot]@users.noreply.github.com",
            )
            self.assertEqual(broker.branch_for_issue(362), "work/issue-362")
            branch_re = broker.get_branch_re()
            self.assertIsNotNone(branch_re.fullmatch("work/issue-362"))
            self.assertEqual(branch_re.fullmatch("work/issue-362").group(1), "362")
            self.assertIsNone(branch_re.fullmatch(""))
            self.assertIsNone(branch_re.fullmatch("work/issue-"))
            self.assertIsNone(branch_re.fullmatch("main"))
            self.assertIsNone(broker.get_planning_issue())

            # Planning commands fail closed when planning issue is blank/disabled
            g = FakeGH()
            with self.assertRaises(broker.BrokerError) as ctx:
                self.v2(
                    {"version": 2, "operation": "plan.create_milestone", "title": "v1"},
                    source_issue=377,
                    gh=g,
                )
            self.assertIn("not configured", str(ctx.exception))
            cmd = broker.V2Command(
                "plan.create_milestone", 377, {"title": "v1"}, 8, "digest"
            )
            with self.assertRaises(broker.BrokerError) as ctx:
                broker.validate_planning(g, cmd)
            self.assertIn("not configured", str(ctx.exception))

        ws_env = {
            "AGENT_BROKER_OWNER": "  jasonbridges  ",
            "AGENT_BOT_NAME": "   ",
            "AGENT_BOT_EMAIL": "\t  \n",
            "AGENT_BROKER_BRANCH_PATTERN": "   ",
            "AGENT_BROKER_BRANCH_RE": " \t ",
            "AGENT_BROKER_PLANNING_ISSUE": "   ",
        }
        with unittest.mock.patch.dict(broker.os.environ, ws_env, clear=False):
            self.assertEqual(broker.get_owner(), "jasonbridges")
            self.assertEqual(broker.get_bot_name(), "jasonbridges-agent[bot]")
            self.assertEqual(
                broker.get_bot_email(),
                "331491158+jasonbridges-agent[bot]@users.noreply.github.com",
            )
            self.assertEqual(broker.branch_for_issue(362), "work/issue-362")
            self.assertIsNotNone(broker.get_branch_re().fullmatch("work/issue-362"))
            self.assertIsNone(broker.get_planning_issue())

    def test_configuration_module_level_initialization_with_empty_template_env(self):
        empty_env = {
            "AGENT_BROKER_OWNER": "jasonbridges",
            "AGENT_BOT_NAME": "",
            "AGENT_BOT_EMAIL": "",
            "AGENT_BROKER_BRANCH_PATTERN": "",
            "AGENT_BROKER_BRANCH_RE": "",
            "AGENT_BROKER_PLANNING_ISSUE": "",
        }
        with unittest.mock.patch.dict(broker.os.environ, empty_env, clear=False):
            spec = importlib.util.spec_from_file_location(
                "agent_command_broker_isolated", SCRIPT
            )
            self.assertIsNotNone(spec)
            self.assertIsNotNone(spec.loader)
            mod = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = mod
            try:
                spec.loader.exec_module(mod)
                self.assertEqual(mod.BOT_NAME, "jasonbridges-agent[bot]")
                self.assertEqual(
                    mod.BOT_EMAIL,
                    "331491158+jasonbridges-agent[bot]@users.noreply.github.com",
                )
                self.assertEqual(mod.BRANCH_RE.pattern, r"^work/issue-(\d+)$")
                self.assertIsNotNone(mod.BRANCH_RE.fullmatch("work/issue-362"))
                self.assertIsNone(mod.BRANCH_RE.fullmatch(""))
                self.assertEqual(mod.branch_for_issue(362), "work/issue-362")
                self.assertIsNone(mod.PLANNING_ISSUE)
                self.assertIsNone(mod.get_planning_issue())
            finally:
                sys.modules.pop(spec.name, None)

    def test_configuration_non_default_and_backward_compatibility_aliases(self):
        custom_env = {
            "AGENT_BROKER_OWNER": "custom-owner",
            "AGENT_BOT_NAME": "custom-bot[bot]",
            "AGENT_BOT_EMAIL": "custom-bot@users.noreply.github.com",
            "AGENT_BROKER_BRANCH_PATTERN": "task/issue-{issue}",
            "AGENT_BROKER_BRANCH_RE": r"^task/issue-(\d+)$",
            "AGENT_BROKER_PLANNING_ISSUE": "456",
        }
        with unittest.mock.patch.dict(broker.os.environ, custom_env, clear=False):
            self.assertEqual(broker.get_owner(), "custom-owner")
            self.assertEqual(broker.get_bot_name(), "custom-bot[bot]")
            self.assertEqual(
                broker.get_bot_email(), "custom-bot@users.noreply.github.com"
            )
            self.assertEqual(broker.branch_for_issue(456), "task/issue-456")
            m = broker.get_branch_re().fullmatch("task/issue-456")
            self.assertIsNotNone(m)
            self.assertEqual(m.group(1), "456")
            self.assertEqual(broker.get_planning_issue(), 456)

            g = FakeGH()
            g.other_issues[456] = {
                "number": 456,
                "state": "open",
                "title": "planning",
                "body": "## Summary\nqueue",
            }
            e = v2_event(
                {"version": 2, "operation": "plan.create_milestone", "title": "v2"},
                source_issue=456,
            )
            e["comment"]["user"]["login"] = "custom-owner"
            cmd = broker.from_event(e)
            broker.validate_planning(g, cmd)

        compat_env = {
            "AGENT_BOT_NAME": "",
            "AGENT_BROKER_BOT_NAME": "legacy-bot[bot]",
            "AGENT_BOT_EMAIL": "",
            "AGENT_BROKER_BOT_EMAIL": "legacy-bot@users.noreply.github.com",
        }
        with unittest.mock.patch.dict(broker.os.environ, compat_env, clear=False):
            self.assertEqual(broker.get_bot_name(), "legacy-bot[bot]")
            self.assertEqual(
                broker.get_bot_email(), "legacy-bot@users.noreply.github.com"
            )

    def test_managed_branch_regex_requires_numeric_issue_capture(self):
        with (
            unittest.mock.patch.dict(
                broker.os.environ,
                {"AGENT_BROKER_BRANCH_RE": r"^task/issue-\d+$"},
                clear=False,
            ),
            self.assertRaises(broker.BrokerError),
        ):
            broker.get_branch_re()

        with unittest.mock.patch.dict(
            broker.os.environ,
            {"AGENT_BROKER_BRANCH_RE": r"^task/issue-(\w+)$"},
            clear=False,
        ):
            g = FakeGH()
            g.pulls = [{"number": 10, "head": {"ref": "task/issue-abc"}}]
            g.pull_file_map[10] = {"other.txt"}
            with self.assertRaises(broker.BrokerError):
                broker.validate_remote(g, self.req())

    def test_configuration_invalid_values_fail_closed_at_use_or_validation(self):
        with unittest.mock.patch.dict(
            broker.os.environ, {"AGENT_BROKER_BRANCH_RE": "["}, clear=False
        ):
            self.assertRaises(broker.BrokerError, broker.get_branch_re)

        for bad_val in ("not-a-number", "-5", "3.14", "bad"):
            with unittest.mock.patch.dict(
                broker.os.environ, {"AGENT_BROKER_PLANNING_ISSUE": bad_val}, clear=False
            ):
                self.assertRaises(broker.BrokerError, broker.get_planning_issue)

        for disabled_val in ("0", "disabled", "Disabled", "DISABLED"):
            with unittest.mock.patch.dict(
                broker.os.environ,
                {"AGENT_BROKER_PLANNING_ISSUE": disabled_val},
                clear=False,
            ):
                self.assertIsNone(broker.get_planning_issue())

        with unittest.mock.patch.dict(
            broker.os.environ,
            {"AGENT_BROKER_BRANCH_PATTERN": "task/{wrong_field}"},
            clear=False,
        ):
            self.assertRaises(broker.BrokerError, broker.branch_for_issue, 362)


if __name__ == "__main__":
    unittest.main()
