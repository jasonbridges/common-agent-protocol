#!/usr/bin/env python3
"""Trusted issue-scoped GitHub App authoring broker.

Executed only from the trusted default branch. Candidate contents are immutable
Git blob references and are never checked out or executed by this process.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import contextlib
import fnmatch
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any


class BrokerError(RuntimeError):
    pass


DEFAULT_OWNER = "jasonbridges"
DEFAULT_BOT_NAME = "jasonbridges-agent[bot]"
DEFAULT_BOT_EMAIL = "331491158+jasonbridges-agent[bot]@users.noreply.github.com"
DEFAULT_BRANCH_PATTERN = "work/issue-{issue}"
DEFAULT_BRANCH_RE = r"^work/issue-(\d+)$"
DEFAULT_BRANCH_RE_PATTERN = re.compile(DEFAULT_BRANCH_RE)
DEFAULT_PLANNING_ISSUE = 377

REPO = os.environ.get("GITHUB_REPOSITORY", "jasonbridges/homelab-infra")
OWNER = (os.environ.get("AGENT_BROKER_OWNER") or "").strip() or (
    REPO.split("/")[0] if "/" in REPO else DEFAULT_OWNER
)


def _init_bot_name() -> str:
    for key in ("AGENT_BOT_NAME", "AGENT_BROKER_BOT_NAME"):
        raw = os.environ.get(key)
        if raw is not None and raw.strip():
            return raw.strip()
    return DEFAULT_BOT_NAME


BOT_NAME = _init_bot_name()


def _init_bot_email() -> str:
    for key in ("AGENT_BOT_EMAIL", "AGENT_BROKER_BOT_EMAIL"):
        raw = os.environ.get(key)
        if raw is not None and raw.strip():
            return raw.strip()
    return DEFAULT_BOT_EMAIL


BOT_EMAIL = _init_bot_email()
PREFIX = "/agent-commit-v1\n"
HIDDEN_PREFIX = "<!-- agent-command-envelope:v1:"
HIDDEN_SUFFIX = " -->"
BASE64URL_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
EXCEPTION_RE = re.compile(r"(?im)^\s*Coordination-Exception:\s*(.+)$")
ISSUE_REF_RE = re.compile(r"#(\d+)")
BACKTICK_RE = re.compile(r"`([^`]+)`")
LABEL_RE = re.compile(r"^\s*([A-Za-z][A-Za-z ]{0,40}):\s*(.*)$")
BULLET_RE = re.compile(r"^\s*(?:[-*\u2022\u00b7]|\d+[.)])\s+(.+?)\s*$")


def _init_branch_re() -> re.Pattern[str]:
    raw = os.environ.get("AGENT_BROKER_BRANCH_RE")
    if raw is not None and raw.strip():
        try:
            return re.compile(raw.strip())
        except re.error:
            return DEFAULT_BRANCH_RE_PATTERN
    return DEFAULT_BRANCH_RE_PATTERN


BRANCH_RE = _init_branch_re()


def get_repo() -> str:
    return os.environ.get("GITHUB_REPOSITORY", REPO)


def get_owner() -> str:
    raw = os.environ.get("AGENT_BROKER_OWNER")
    if raw is not None and raw.strip():
        return raw.strip()
    repo = get_repo()
    if "/" in repo:
        return repo.split("/")[0]
    return OWNER if (isinstance(OWNER, str) and OWNER.strip()) else DEFAULT_OWNER


def get_bot_name() -> str:
    for key in ("AGENT_BOT_NAME", "AGENT_BROKER_BOT_NAME"):
        raw = os.environ.get(key)
        if raw is not None and raw.strip():
            return raw.strip()
    if "BOT_NAME" in globals() and isinstance(BOT_NAME, str) and BOT_NAME.strip():
        return BOT_NAME.strip()
    return DEFAULT_BOT_NAME


def get_bot_email() -> str:
    for key in ("AGENT_BOT_EMAIL", "AGENT_BROKER_BOT_EMAIL"):
        raw = os.environ.get(key)
        if raw is not None and raw.strip():
            return raw.strip()
    if "BOT_EMAIL" in globals() and isinstance(BOT_EMAIL, str) and BOT_EMAIL.strip():
        return BOT_EMAIL.strip()
    return DEFAULT_BOT_EMAIL


def get_branch_pattern() -> str:
    raw = os.environ.get("AGENT_BROKER_BRANCH_PATTERN")
    if raw is not None and raw.strip():
        return raw.strip()
    return DEFAULT_BRANCH_PATTERN


def branch_for_issue(issue_number: int) -> str:
    pattern = get_branch_pattern()
    try:
        return pattern.format(issue=issue_number)
    except (KeyError, ValueError, IndexError) as exc:
        raise BrokerError(f"Invalid AGENT_BROKER_BRANCH_PATTERN: {pattern!r}") from exc


def get_branch_re() -> re.Pattern[str]:
    raw = os.environ.get("AGENT_BROKER_BRANCH_RE")
    if raw is None or not raw.strip():
        compiled = (
            BRANCH_RE
            if "BRANCH_RE" in globals()
            and isinstance(BRANCH_RE, re.Pattern)
            and BRANCH_RE.pattern
            else DEFAULT_BRANCH_RE_PATTERN
        )
    else:
        try:
            compiled = re.compile(raw.strip())
        except re.error as exc:
            raise BrokerError(f"Invalid AGENT_BROKER_BRANCH_RE: {raw!r}") from exc
    if compiled.groups < 1:
        raise BrokerError(
            "AGENT_BROKER_BRANCH_RE must capture the issue number in group 1"
        )
    return compiled


def managed_branch_issue(branch: str) -> int | None:
    match = get_branch_re().fullmatch(branch)
    if match is None:
        return None
    try:
        issue = int(match.group(1))
    except (IndexError, TypeError, ValueError) as exc:
        raise BrokerError(
            f"Managed branch {branch!r} has an invalid issue-number capture"
        ) from exc
    if issue <= 0:
        raise BrokerError(f"Managed branch {branch!r} has a non-positive issue number")
    return issue


def _init_planning_issue() -> int | None:
    raw = os.environ.get("AGENT_BROKER_PLANNING_ISSUE")
    if raw is None:
        return DEFAULT_PLANNING_ISSUE
    raw = raw.strip()
    if not raw or raw == "0" or raw.lower() == "disabled":
        return None
    try:
        val = int(raw)
        return val if val > 0 else None
    except ValueError:
        return None


PLANNING_ISSUE = _init_planning_issue()


def get_planning_issue() -> int | None:
    if "AGENT_BROKER_PLANNING_ISSUE" in os.environ:
        raw = os.environ["AGENT_BROKER_PLANNING_ISSUE"].strip()
        if not raw or raw == "0" or raw.lower() == "disabled":
            return None
        try:
            val = int(raw)
        except ValueError as exc:
            raise BrokerError(f"Invalid AGENT_BROKER_PLANNING_ISSUE: {raw!r}") from exc
        if val <= 0:
            raise BrokerError(f"Invalid AGENT_BROKER_PLANNING_ISSUE: {raw!r}")
        return val
    return PLANNING_ISSUE


REQUIRED_SECTIONS = (
    "Issue",
    "Claim",
    "Changed paths",
    "Tests",
    "Rollback",
    "SSO impact",
    "Coordination",
)
ALLOWED_MODES = {"100644", "100755"}
DENIED_PREFIXES = (".github/workflows/",)
MAX_COMMENT = 60_000
MAX_DECODED_ENVELOPE = 44_000
MAX_BODY = 30_000
MAX_FILES = 64
MAX_BLOB = 2 * 1024 * 1024
MAX_TOTAL = 8 * 1024 * 1024
PROVENANCE_PREFIX = "<!-- agent-claim-provenance:v1:"
PROVENANCE_SUFFIX = " -->"
V2_OPERATIONS = {
    "plan.create_milestone",
    "plan.create_issue",
    "plan.update_issue",
    "plan.assign_milestone",
    "work.update",
    "work.resume",
}
REQUIRED_ISSUE_SECTIONS = (
    "Summary",
    "Acceptance criteria",
    "Scope ownership",
    "Validation",
    "Rollback",
    "SSO impact",
    "Coordination",
)


@dataclass(frozen=True)
class File:
    path: str
    sha: str | None
    mode: str = "100644"


@dataclass(frozen=True)
class Request:
    issue: int
    base_sha: str
    message: str
    files: tuple[File, ...]
    title: str
    body: str
    comment_id: int
    comment_digest: str

    @property
    def branch(self) -> str:
        return branch_for_issue(self.issue)

    @property
    def paths(self) -> set[str]:
        return {f.path for f in self.files}

    def json(self) -> dict[str, Any]:
        return {
            "version": 1,
            "issue": self.issue,
            "base_sha": self.base_sha,
            "commit_message": self.message,
            "files": [
                {"path": f.path, "sha": f.sha, "mode": f.mode} for f in self.files
            ],
            "pr": {"title": self.title, "body": self.body},
            "source_comment_id": self.comment_id,
            "source_comment_sha256": self.comment_digest,
        }


@dataclass(frozen=True)
class V2Command:
    operation: str
    source_issue: int
    payload: dict[str, Any]
    comment_id: int
    comment_digest: str

    @property
    def issue(self) -> int | None:
        value = self.payload.get("issue")
        return int(value) if value is not None else None


Command = Request | V2Command


class GH:
    def __init__(self, token: str):
        if not token:
            raise BrokerError("GitHub token is required")
        self.token = token
        self.root = f"https://api.github.com/repos/{get_repo()}"

    def call(
        self, method: str, path: str, payload: Any = None, allow_404: bool = False
    ) -> Any:
        url = path if path.startswith("https://") else self.root + path
        data = (
            None
            if payload is None
            else json.dumps(payload, separators=(",", ":")).encode()
        )
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": f"{get_repo().split('/')[-1]}-agent-command-broker",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            with urllib.request.urlopen(
                urllib.request.Request(url, data=data, headers=headers, method=method),
                timeout=30,
            ) as r:
                raw = r.read()
                return None if not raw else json.loads(raw)
        except urllib.error.HTTPError as e:
            if allow_404 and e.code == 404:
                return None
            detail = e.read().decode(errors="replace")[:1500]
            raise BrokerError(
                f"GitHub API {e.code} for {method} {path}: {detail}"
            ) from e
        except urllib.error.URLError as e:
            raise BrokerError(f"GitHub API request failed: {e.reason}") from e

    def get(self, path: str, allow_404: bool = False) -> Any:
        return self.call("GET", path, allow_404=allow_404)

    def post(self, path: str, payload: Any) -> Any:
        return self.call("POST", path, payload)

    def patch(self, path: str, payload: Any) -> Any:
        return self.call("PATCH", path, payload)

    def pages(self, path: str):
        sep = "&" if "?" in path else "?"
        page = 1
        while True:
            rows = self.get(f"{path}{sep}per_page=100&page={page}")
            if not isinstance(rows, list):
                raise BrokerError(f"Expected list response for {path}")
            yield from rows
            if len(rows) < 100:
                return
            page += 1

    def issue(self, n: int) -> dict[str, Any]:
        row = self.get(f"/issues/{n}")
        if not isinstance(row, dict):
            raise BrokerError(f"Invalid issue #{n} response")
        return row

    def main_sha(self) -> str:
        row = self.get("/git/ref/heads/main")
        try:
            sha = row["object"]["sha"]
        except (KeyError, TypeError) as e:
            raise BrokerError("Unable to resolve main") from e
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise BrokerError("Malformed main SHA")
        return sha

    def branch_ref(self, branch: str, allow_404: bool = False) -> dict[str, Any] | None:
        row = self.get(
            "/git/ref/heads/" + urllib.parse.quote(branch, safe="/"), allow_404
        )
        if row is None:
            return None
        if not isinstance(row, dict):
            raise BrokerError(f"Malformed branch response for {branch}")
        return row

    def branch_exists(self, branch: str) -> bool:
        return self.branch_ref(branch, True) is not None

    def branch_sha(self, branch: str) -> str | None:
        row = self.branch_ref(branch, True)
        if row is None:
            return None
        sha = row.get("object", {}).get("sha")
        if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
            raise BrokerError(f"Malformed branch SHA for {branch}")
        return sha

    def milestone(self, number: int) -> dict[str, Any]:
        row = self.get(f"/milestones/{number}")
        if not isinstance(row, dict):
            raise BrokerError(f"Invalid milestone #{number} response")
        return row

    def pull_files(self, n: int) -> set[str]:
        return {
            r["filename"]
            for r in self.pages(f"/pulls/{n}/files")
            if isinstance(r, dict) and r.get("filename")
        }


def bounded(value: Any, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BrokerError(f"{name} must be a non-empty string")
    if len(value.encode()) > limit:
        raise BrokerError(f"{name} exceeds {limit} bytes")
    return value


def path_value(value: Any) -> str:
    path = bounded(value, "file path", 300)
    if "\\" in path or "\0" in path or path.startswith(("/", "./")):
        raise BrokerError(f"Unsafe path {path!r}")
    pure = PurePosixPath(path)
    if pure.as_posix() != path or any(p in {"", ".", ".."} for p in pure.parts):
        raise BrokerError(f"Unsafe path {path!r}")
    if path.startswith(DENIED_PREFIXES):
        raise BrokerError(f"Broker v1 refuses workflow-definition change {path}")
    return path


def parse_payload(payload: dict[str, Any], comment_id: int, digest: str) -> Request:
    allowed = {"version", "issue", "base_sha", "commit_message", "files", "pr"}
    if not isinstance(payload, dict) or set(payload) - allowed:
        raise BrokerError("Payload contains unknown fields")
    if payload.get("version") != 1:
        raise BrokerError("Only version 1 is supported")
    try:
        issue = int(payload["issue"])
    except (KeyError, TypeError, ValueError) as e:
        raise BrokerError("issue must be a positive integer") from e
    if issue <= 0:
        raise BrokerError("issue must be a positive integer")
    base = str(payload.get("base_sha", ""))
    if not SHA_RE.fullmatch(base):
        raise BrokerError("base_sha must be a lowercase 40-character SHA")
    message = bounded(payload.get("commit_message"), "commit_message", 1024)
    rows = payload.get("files")
    if not isinstance(rows, list) or not rows or len(rows) > MAX_FILES:
        raise BrokerError("files must be a bounded non-empty array")
    files: list[File] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"path", "sha", "mode"}:
            raise BrokerError("Invalid files entry")
        path = path_value(row.get("path"))
        mode = str(row.get("mode", "100644"))
        if mode not in ALLOWED_MODES:
            raise BrokerError(f"Unsupported mode {mode} for {path}")
        sha = row.get("sha")
        if sha is not None and (not isinstance(sha, str) or not SHA_RE.fullmatch(sha)):
            raise BrokerError(f"Invalid blob SHA for {path}")
        files.append(File(path, sha, mode))
    if len({f.path for f in files}) != len(files):
        raise BrokerError("Duplicate file path")
    pr = payload.get("pr")
    if not isinstance(pr, dict) or set(pr) != {"title", "body"}:
        raise BrokerError("pr must contain exactly title and body")
    return Request(
        issue,
        base,
        message,
        tuple(files),
        bounded(pr["title"], "pr.title", 240),
        bounded(pr["body"], "pr.body", MAX_BODY),
        comment_id,
        digest,
    )


def _strict_fields(
    payload: dict[str, Any], required: set[str], optional: set[str] | None = None
) -> None:
    optional = optional or set()
    if not isinstance(payload, dict):
        raise BrokerError("Command payload must be an object")
    keys = set(payload)
    if missing := required - keys:
        raise BrokerError("Payload missing fields: " + ", ".join(sorted(missing)))
    if unknown := keys - required - optional:
        raise BrokerError(
            "Payload contains unknown fields: " + ", ".join(sorted(unknown))
        )


def _positive_int(value: Any, name: str) -> int:
    if isinstance(value, bool):
        raise BrokerError(f"{name} must be a positive integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as exc:
        raise BrokerError(f"{name} must be a positive integer") from exc
    if result <= 0:
        raise BrokerError(f"{name} must be a positive integer")
    return result


def _sha256_value(value: Any, name: str) -> str:
    value = str(value or "")
    if not re.fullmatch(r"[0-9a-f]{64}", value):
        raise BrokerError(f"{name} must be a lowercase SHA-256 digest")
    return value


def _parse_files(rows: Any) -> tuple[File, ...]:
    if not isinstance(rows, list) or not rows or len(rows) > MAX_FILES:
        raise BrokerError("files must be a bounded non-empty array")
    files: list[File] = []
    for row in rows:
        if not isinstance(row, dict) or set(row) - {"path", "sha", "mode"}:
            raise BrokerError("Invalid files entry")
        path = path_value(row.get("path"))
        mode = str(row.get("mode", "100644"))
        if mode not in ALLOWED_MODES:
            raise BrokerError(f"Unsupported mode {mode} for {path}")
        sha = row.get("sha")
        if sha is not None and (not isinstance(sha, str) or not SHA_RE.fullmatch(sha)):
            raise BrokerError(f"Invalid blob SHA for {path}")
        files.append(File(path, sha, mode))
    if len({f.path for f in files}) != len(files):
        raise BrokerError("Duplicate file path")
    return tuple(files)


def _parse_v2(
    payload: dict[str, Any], source_issue: int, comment_id: int, digest: str
) -> V2Command:
    if payload.get("version") != 2:
        raise BrokerError("Unsupported command version")
    operation = str(payload.get("operation") or "")
    if operation not in V2_OPERATIONS:
        raise BrokerError("Unsupported broker operation")

    common = {"version", "operation"}
    if operation == "plan.create_milestone":
        _strict_fields(payload, common | {"title"}, {"description", "due_on"})
        bounded(payload["title"], "title", 200)
        if "description" in payload:
            bounded(payload["description"], "description", 4000)
        if "due_on" in payload:
            due = bounded(payload["due_on"], "due_on", 64)
            try:
                parsed = datetime.fromisoformat(due.replace("Z", "+00:00"))
            except ValueError as exc:
                raise BrokerError("due_on must be ISO-8601") from exc
            if parsed.tzinfo is None:
                raise BrokerError("due_on must include a timezone")
    elif operation == "plan.create_issue":
        _strict_fields(
            payload, common | {"title", "body", "implementation"}, {"milestone"}
        )
        bounded(payload["title"], "title", 240)
        bounded(payload["body"], "body", MAX_BODY)
        if not isinstance(payload["implementation"], bool):
            raise BrokerError("implementation must be boolean")
        if "milestone" in payload:
            _positive_int(payload["milestone"], "milestone")
    elif operation == "plan.update_issue":
        _strict_fields(
            payload,
            common | {"target_issue", "expected_body_sha256"},
            {"expected_title", "title", "body"},
        )
        _positive_int(payload["target_issue"], "target_issue")
        _sha256_value(payload["expected_body_sha256"], "expected_body_sha256")
        if "title" not in payload and "body" not in payload:
            raise BrokerError("plan.update_issue requires title and/or body")
        if "title" in payload:
            bounded(payload["title"], "title", 240)
            if "expected_title" not in payload:
                raise BrokerError("expected_title is required when changing title")
            bounded(payload["expected_title"], "expected_title", 240)
        if "body" in payload:
            bounded(payload["body"], "body", MAX_BODY)
    elif operation == "plan.assign_milestone":
        _strict_fields(payload, common | {"target_issue", "milestone"})
        _positive_int(payload["target_issue"], "target_issue")
        _positive_int(payload["milestone"], "milestone")
    elif operation == "work.update":
        _strict_fields(
            payload,
            common | {"issue", "expected_head_sha", "commit_message", "files"},
            {"pr"},
        )
        _positive_int(payload["issue"], "issue")
        if not SHA_RE.fullmatch(str(payload["expected_head_sha"])):
            raise BrokerError("expected_head_sha must be a lowercase 40-character SHA")
        bounded(payload["commit_message"], "commit_message", 1024)
        _parse_files(payload["files"])
        if "pr" in payload:
            pr = payload["pr"]
            if not isinstance(pr, dict) or set(pr) != {"title", "body"}:
                raise BrokerError("pr must contain exactly title and body")
            bounded(pr["title"], "pr.title", 240)
            bounded(pr["body"], "pr.body", MAX_BODY)
    elif operation == "work.resume":
        _strict_fields(
            payload,
            common
            | {
                "issue",
                "expected_head_sha",
                "original_comment_id",
                "original_comment_sha256",
                "request_sha256",
            },
        )
        _positive_int(payload["issue"], "issue")
        _positive_int(payload["original_comment_id"], "original_comment_id")
        if not SHA_RE.fullmatch(str(payload["expected_head_sha"])):
            raise BrokerError("expected_head_sha must be a lowercase 40-character SHA")
        _sha256_value(payload["original_comment_sha256"], "original_comment_sha256")
        _sha256_value(payload["request_sha256"], "request_sha256")

    if operation.startswith("plan."):
        planning_num = get_planning_issue()
        if planning_num is None:
            raise BrokerError(
                "Planning commands are not configured for this repository"
            )
        if source_issue != planning_num:
            raise BrokerError(
                f"Planning commands must originate from issue #{planning_num}"
            )
    elif _positive_int(payload.get("issue"), "issue") != source_issue:
        raise BrokerError("Work command issue does not match comment issue")
    return V2Command(operation, source_issue, dict(payload), comment_id, digest)


def _decode_hidden_envelope(remainder: str) -> Any:
    if not remainder.startswith(HIDDEN_PREFIX) or not remainder.endswith(HIDDEN_SUFFIX):
        raise BrokerError("Malformed hidden broker envelope")
    encoded = remainder[len(HIDDEN_PREFIX) : -len(HIDDEN_SUFFIX)]
    if not encoded or not BASE64URL_RE.fullmatch(encoded):
        raise BrokerError("Malformed hidden broker envelope encoding")
    try:
        raw = base64.b64decode(
            encoded + ("=" * (-len(encoded) % 4)), altchars=b"-_", validate=True
        )
    except (binascii.Error, ValueError) as exc:
        raise BrokerError("Malformed hidden broker envelope encoding") from exc
    if len(raw) > MAX_DECODED_ENVELOPE:
        raise BrokerError("Decoded broker envelope exceeds size limit")
    try:
        return json.loads(raw.decode("utf-8", errors="strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError("Malformed hidden broker envelope payload") from exc


def _payload_from_body(body: str) -> Any:
    remainder = body[len(PREFIX) :]
    if remainder.startswith("<!--"):
        return _decode_hidden_envelope(remainder)
    try:
        return json.loads(remainder)
    except json.JSONDecodeError as exc:
        raise BrokerError("Malformed broker command") from exc


def from_event(event: dict[str, Any]) -> Command:
    issue, comment = event.get("issue"), event.get("comment")
    if (
        not isinstance(issue, dict)
        or not isinstance(comment, dict)
        or "pull_request" in issue
    ):
        raise BrokerError("Broker accepts commands only on issues")
    if issue.get("state") != "open":
        raise BrokerError("Target issue must be open")
    owner = get_owner()
    if (
        comment.get("user", {}).get("login") != owner
        or comment.get("author_association") != "OWNER"
    ):
        raise BrokerError("Only repository owner comments may invoke the broker")
    body = str(comment.get("body") or "")
    if len(body.encode()) > MAX_COMMENT or not body.startswith(PREFIX):
        raise BrokerError("Invalid or oversized broker command")
    try:
        payload = _payload_from_body(body)
        comment_id = int(comment["id"])
        event_issue = int(issue["number"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BrokerError("Malformed broker command") from exc
    digest = hashlib.sha256(body.encode()).hexdigest()
    if not isinstance(payload, dict):
        raise BrokerError("Command payload must be an object")
    if payload.get("version") == 1:
        req = parse_payload(payload, comment_id, digest)
        if req.issue != event_issue:
            raise BrokerError("Command issue does not match comment issue")
        return req
    return _parse_v2(payload, event_issue, comment_id, digest)


def _tokens(text: str) -> set[str]:
    quoted = {x.strip() for x in BACKTICK_RE.findall(text) if x.strip()}
    if quoted:
        return quoted
    return {
        x.strip().rstrip(".")
        for x in text.split(",")
        if "/" in x or "*" in x or x.strip().startswith(".")
    }


def scope(body: str) -> tuple[set[str], set[str]]:
    if "## Scope ownership" not in body:
        return set(), set()
    section = body.split("## Scope ownership", 1)[1]
    m = re.search(r"(?m)^##\s+", section)
    section = section[: m.start()] if m else section
    result = {"exclusive": set(), "shared": set()}
    active: str | None = None
    for line in section.splitlines():
        label = LABEL_RE.match(line)
        if label:
            key = label.group(1).strip().lower()
            active = key if key in result else None
            if active:
                result[active].update(_tokens(label.group(2)))
            continue
        bullet = BULLET_RE.match(line)
        if active and bullet:
            result[active].update(_tokens(bullet.group(1)))
    return result["exclusive"], result["shared"]


def matches(path: str, patterns: set[str]) -> bool:
    for p in patterns:
        if fnmatch.fnmatch(path, p.rstrip("/")):
            return True
        if p.endswith("/**") and path.startswith(p[:-3].rstrip("/") + "/"):
            return True
        if p.endswith("/") and path.startswith(p):
            return True
    return False


def exceptions(body: str) -> set[int]:
    out: set[int] = set()
    for m in EXCEPTION_RE.finditer(body):
        out.update(int(x) for x in ISSUE_REF_RE.findall(m.group(1)))
    return out


def validate_pr(req: Request) -> None:
    missing = [
        h
        for h in REQUIRED_SECTIONS
        if not re.search(rf"(?im)^##\s+{re.escape(h)}\s*$", req.body)
    ]
    if missing:
        raise BrokerError("PR body missing sections: " + ", ".join(missing))
    if not re.search(
        rf"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#{req.issue}\b", req.body
    ):
        raise BrokerError("PR body does not close canonical issue")
    if req.branch not in req.body:
        raise BrokerError("PR body does not name canonical branch")


def _git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(
        b"blob " + str(len(content)).encode() + b"\0" + content
    ).hexdigest()


def _decode_github_blob_content(value: Any, path: str) -> bytes:
    if not isinstance(value, str):
        raise BrokerError(f"Malformed blob content for {path}")
    try:
        encoded = value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise BrokerError(f"Malformed blob content for {path}") from exc
    compact = b"".join(encoded.split())
    try:
        return base64.b64decode(compact, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise BrokerError(f"Malformed blob content for {path}") from exc


def materialize_file_set(gh: GH, files: tuple[File, ...]) -> dict[str, dict[str, str]]:
    materialized: dict[str, dict[str, str]] = {}
    total = 0
    for file in files:
        if file.sha is None:
            continue
        blob = gh.get(f"/git/blobs/{file.sha}")
        if not isinstance(blob, dict) or blob.get("sha") != file.sha:
            raise BrokerError(f"Blob identity mismatch for {file.path}")
        if blob.get("encoding") != "base64" or not isinstance(blob.get("content"), str):
            raise BrokerError(f"Unsupported blob encoding for {file.path}")
        content = _decode_github_blob_content(blob["content"], file.path)
        if len(content) > MAX_BLOB or _git_blob_sha(content) != file.sha:
            raise BrokerError(f"Blob content integrity failure for {file.path}")
        total += len(content)
        materialized[file.path] = {
            "sha": file.sha,
            "content_b64": base64.b64encode(content).decode("ascii"),
        }
    if total > MAX_TOTAL:
        raise BrokerError("Aggregate blob size exceeds limit")
    return materialized


def materialize_blobs(gh: GH, req: Request) -> dict[str, dict[str, str]]:
    return materialize_file_set(gh, req.files)


def _verify_materialized_files(
    files: tuple[File, ...], materialized: dict[str, Any]
) -> None:
    expected = {f.path: f for f in files if f.sha is not None}
    if set(materialized) != set(expected):
        raise BrokerError("Materialized blob set mismatch")
    total = 0
    for path, file in expected.items():
        row = materialized.get(path)
        if (
            not isinstance(row, dict)
            or set(row) != {"sha", "content_b64"}
            or row.get("sha") != file.sha
        ):
            raise BrokerError(f"Malformed materialized blob for {path}")
        try:
            content = base64.b64decode(str(row["content_b64"]), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise BrokerError(f"Malformed materialized blob for {path}") from exc
        if len(content) > MAX_BLOB or _git_blob_sha(content) != file.sha:
            raise BrokerError(f"Materialized blob integrity failure for {path}")
        total += len(content)
    if total > MAX_TOTAL:
        raise BrokerError("Aggregate materialized blob size exceeds limit")


def _verify_materialized(req: Request, materialized: dict[str, Any]) -> None:
    _verify_materialized_files(req.files, materialized)


def recreate_file_set(
    gh: GH, files: tuple[File, ...], materialized: dict[str, Any]
) -> None:
    _verify_materialized_files(files, materialized)
    for file in files:
        if file.sha is None:
            continue
        row = materialized[file.path]
        last_error: BrokerError | None = None
        for attempt in range(2):
            try:
                created = gh.post(
                    "/git/blobs", {"content": row["content_b64"], "encoding": "base64"}
                )
                if not isinstance(created, dict) or created.get("sha") != file.sha:
                    raise BrokerError(
                        f"App-created blob identity mismatch for {file.path}"
                    )
                last_error = None
                break
            except BrokerError as exc:
                last_error = exc
                if attempt == 0:
                    time.sleep(0.25)
        if last_error is not None:
            raise last_error


def recreate_blobs(gh: GH, req: Request, materialized: dict[str, Any]) -> None:
    recreate_file_set(gh, req.files, materialized)


def validate_remote(
    gh: GH, req: Request, *, verify_blobs: bool = True
) -> dict[str, Any]:
    if gh.main_sha() != req.base_sha:
        raise BrokerError("Stale base SHA")
    if gh.branch_exists(req.branch):
        raise BrokerError("Canonical claim branch already exists")
    issue = gh.issue(req.issue)
    if issue.get("pull_request") or issue.get("state") != "open":
        raise BrokerError("Canonical issue is not an open implementation issue")
    body = str(issue.get("body") or "")
    exclusive, shared = scope(body)
    if not exclusive and not shared:
        raise BrokerError("Issue lacks usable ## Scope ownership")
    escaped = sorted(p for p in req.paths if not matches(p, exclusive | shared))
    if escaped:
        raise BrokerError("Paths escape issue scope: " + ", ".join(escaped))
    validate_pr(req)

    if verify_blobs:
        materialize_blobs(gh, req)

    current_exc = exceptions(body)
    for pr in gh.pages("/pulls?state=open"):
        if not isinstance(pr, dict):
            continue
        number = int(pr.get("number", 0))
        branch = str(pr.get("head", {}).get("ref", ""))
        other_files = gh.pull_files(number)
        other_issue = None
        other_exclusive: set[str] = set()
        reciprocal = False
        other_issue = managed_branch_issue(branch)
        if other_issue is not None:
            other_body = str(gh.issue(other_issue).get("body") or "")
            other_exclusive, _ = scope(other_body)
            reciprocal = other_issue in current_exc and req.issue in exceptions(
                other_body
            )
        collided = req.paths & other_files
        collided |= {p for p in other_files if matches(p, exclusive)}
        collided |= {p for p in req.paths if matches(p, other_exclusive)}
        if collided and not reciprocal:
            raise BrokerError(
                f"Path collision with PR #{number}: {', '.join(sorted(collided))}"
            )
    return issue


def _body_digest(body: str) -> str:
    return hashlib.sha256(body.encode()).hexdigest()


def _request_payload(req: Request) -> dict[str, Any]:
    return {
        "version": 1,
        "issue": req.issue,
        "base_sha": req.base_sha,
        "commit_message": req.message,
        "files": [{"path": f.path, "sha": f.sha, "mode": f.mode} for f in req.files],
        "pr": {"title": req.title, "body": req.body},
    }


def request_sha256(req: Request) -> str:
    encoded = json.dumps(
        _request_payload(req), sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_issue_body(body: str) -> None:
    missing = [
        heading
        for heading in REQUIRED_ISSUE_SECTIONS
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", body)
    ]
    if missing:
        raise BrokerError(
            "Implementation issue body missing sections: " + ", ".join(missing)
        )
    exclusive, shared = scope(body)
    if not exclusive and not shared:
        raise BrokerError("Implementation issue body lacks usable ## Scope ownership")


def _open_issue(gh: GH, number: int) -> dict[str, Any]:
    issue = gh.issue(number)
    if issue.get("pull_request") or issue.get("state") != "open":
        raise BrokerError(f"Issue #{number} must be an open non-PR issue")
    return issue


def _open_milestone(gh: GH, number: int) -> dict[str, Any]:
    milestone = gh.milestone(number)
    if milestone.get("state") != "open":
        raise BrokerError(f"Milestone #{number} must be open")
    return milestone


def _pr_maps_issue(pr: dict[str, Any], issue: int, branch: str) -> bool:
    if str(pr.get("base", {}).get("ref", "")) != "main":
        return False
    if str(pr.get("head", {}).get("ref", "")) != branch:
        return False
    head_repo = pr.get("head", {}).get("repo") or {}
    if head_repo.get("full_name") != get_repo():
        return False
    body = str(pr.get("body") or "")
    return branch in body and bool(
        re.search(
            rf"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#{issue}\b", body
        )
    )


def _canonical_open_pr(gh: GH, issue: int, branch: str) -> dict[str, Any]:
    matches = [
        pr
        for pr in gh.pages("/pulls?state=open")
        if isinstance(pr, dict) and str(pr.get("head", {}).get("ref", "")) == branch
    ]
    if len(matches) != 1:
        raise BrokerError(
            f"Expected exactly one open PR for {branch}; found {len(matches)}"
        )
    pr = matches[0]
    if not _pr_maps_issue(pr, issue, branch):
        raise BrokerError("Canonical PR does not map to the implementation issue/main")
    return pr


def _validate_pr_metadata(issue: int, branch: str, title: str, body: str) -> None:
    bounded(title, "pr.title", 240)
    bounded(body, "pr.body", MAX_BODY)
    missing = [
        heading
        for heading in REQUIRED_SECTIONS
        if not re.search(rf"(?im)^##\s+{re.escape(heading)}\s*$", body)
    ]
    if missing:
        raise BrokerError("PR body missing sections: " + ", ".join(missing))
    if not re.search(
        rf"(?im)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#{issue}\b", body
    ):
        raise BrokerError("PR body does not close canonical issue")
    if branch not in body:
        raise BrokerError("PR body does not name canonical branch")


def _validate_scope_and_collisions(
    gh: GH,
    issue_number: int,
    paths: set[str],
    *,
    exclude_pr: int | None = None,
) -> dict[str, Any]:
    issue = _open_issue(gh, issue_number)
    body = str(issue.get("body") or "")
    exclusive, shared = scope(body)
    if not exclusive and not shared:
        raise BrokerError("Issue lacks usable ## Scope ownership")
    escaped = sorted(path for path in paths if not matches(path, exclusive | shared))
    if escaped:
        raise BrokerError("Paths escape issue scope: " + ", ".join(escaped))

    current_exc = exceptions(body)
    for pr in gh.pages("/pulls?state=open"):
        if not isinstance(pr, dict):
            continue
        number = int(pr.get("number", 0))
        if exclude_pr is not None and number == exclude_pr:
            continue
        branch = str(pr.get("head", {}).get("ref", ""))
        other_files = gh.pull_files(number)
        other_exclusive: set[str] = set()
        reciprocal = False
        other_issue = managed_branch_issue(branch)
        if other_issue is not None:
            other_body = str(gh.issue(other_issue).get("body") or "")
            other_exclusive, _ = scope(other_body)
            reciprocal = other_issue in current_exc and issue_number in exceptions(
                other_body
            )
        collided = paths & other_files
        collided |= {path for path in other_files if matches(path, exclusive)}
        collided |= {path for path in paths if matches(path, other_exclusive)}
        if collided and not reciprocal:
            raise BrokerError(
                f"Path collision with PR #{number}: {', '.join(sorted(collided))}"
            )
    return issue


def _files_for_v2(cmd: V2Command) -> tuple[File, ...]:
    if cmd.operation != "work.update":
        return ()
    return _parse_files(cmd.payload["files"])


def validate_planning(gh: GH, cmd: V2Command) -> None:
    planning_num = get_planning_issue()
    if planning_num is None:
        raise BrokerError("Planning commands are not configured for this repository")
    if cmd.source_issue != planning_num:
        raise BrokerError(
            f"Planning commands must originate from issue #{planning_num}"
        )
    _open_issue(gh, planning_num)
    payload = cmd.payload
    if cmd.operation == "plan.create_milestone":
        title = str(payload["title"])
        for milestone in gh.pages("/milestones?state=open"):
            if isinstance(milestone, dict) and str(milestone.get("title", "")) == title:
                raise BrokerError(f"Open milestone with title {title!r} already exists")
    elif cmd.operation == "plan.create_issue":
        proposed_body = str(payload["body"])
        if payload["implementation"] or "## Scope ownership" in proposed_body:
            _validate_issue_body(proposed_body)
        if "milestone" in payload:
            _open_milestone(gh, int(payload["milestone"]))
    elif cmd.operation == "plan.update_issue":
        issue = _open_issue(gh, int(payload["target_issue"]))
        current_body = str(issue.get("body") or "")
        if _body_digest(current_body) != payload["expected_body_sha256"]:
            raise BrokerError("Issue body changed since planning request was prepared")
        if (
            "title" in payload
            and str(issue.get("title") or "") != payload["expected_title"]
        ):
            raise BrokerError("Issue title changed since planning request was prepared")
        if "body" in payload:
            proposed_body = str(payload["body"])
            if (
                "## Scope ownership" in current_body
                or "## Scope ownership" in proposed_body
            ):
                _validate_issue_body(proposed_body)
    elif cmd.operation == "plan.assign_milestone":
        _open_issue(gh, int(payload["target_issue"]))
        _open_milestone(gh, int(payload["milestone"]))
    else:
        raise BrokerError("Not a planning operation")


def validate_work_update(
    gh: GH,
    cmd: V2Command,
    *,
    verify_blobs: bool = True,
) -> tuple[dict[str, Any], dict[str, Any], tuple[File, ...]]:
    if cmd.operation != "work.update":
        raise BrokerError("Not a work.update operation")
    issue_number = int(cmd.payload["issue"])
    branch = branch_for_issue(issue_number)
    expected_head = str(cmd.payload["expected_head_sha"])
    current_head = gh.branch_sha(branch)
    if current_head != expected_head:
        raise BrokerError("Stale or missing canonical branch head")
    pr = _canonical_open_pr(gh, issue_number, branch)
    pr_number = int(pr["number"])
    files = _files_for_v2(cmd)
    issue = _validate_scope_and_collisions(
        gh,
        issue_number,
        {file.path for file in files},
        exclude_pr=pr_number,
    )
    if "pr" in cmd.payload:
        metadata = cmd.payload["pr"]
        _validate_pr_metadata(
            issue_number, branch, str(metadata["title"]), str(metadata["body"])
        )
    if verify_blobs:
        materialize_file_set(gh, files)
    return issue, pr, files


def verify_comment(gh: GH, req: Command) -> None:
    c = gh.get(f"/issues/comments/{req.comment_id}")
    owner = get_owner()
    if (
        not isinstance(c, dict)
        or c.get("user", {}).get("login") != owner
        or c.get("author_association") != "OWNER"
    ):
        raise BrokerError("Source comment authorization changed")
    if (
        hashlib.sha256(str(c.get("body") or "").encode()).hexdigest()
        != req.comment_digest
    ):
        raise BrokerError("Source comment was edited after validation")


def _encode_record(prefix: str, suffix: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
    return prefix + encoded + suffix


def _decode_record(body: str, prefix: str, suffix: str) -> dict[str, Any] | None:
    index = body.find(prefix)
    if index < 0:
        return None
    end = body.find(suffix, index + len(prefix))
    if end < 0:
        raise BrokerError("Malformed broker provenance record")
    encoded = body[index + len(prefix) : end]
    if not encoded or not BASE64URL_RE.fullmatch(encoded):
        raise BrokerError("Malformed broker provenance encoding")
    try:
        raw = base64.b64decode(
            encoded + ("=" * (-len(encoded) % 4)), altchars=b"-_", validate=True
        )
        decoded = json.loads(raw.decode("utf-8"))
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BrokerError("Malformed broker provenance payload") from exc
    if not isinstance(decoded, dict):
        raise BrokerError("Malformed broker provenance payload")
    return decoded


def _claim_provenance(req: Request) -> dict[str, Any]:
    return {
        "version": 1,
        "issue": req.issue,
        "branch": req.branch,
        "base_sha": req.base_sha,
        "source_comment_id": req.comment_id,
        "source_comment_sha256": req.comment_digest,
        "request_sha256": request_sha256(req),
        "paths": sorted(req.paths),
    }


def _claim_body(req: Request) -> str:
    provenance = _encode_record(
        PROVENANCE_PREFIX, PROVENANCE_SUFFIX, _claim_provenance(req)
    )
    bot = get_bot_name()
    return (
        "BOT CLAIM\n\n"
        f"- Agent: `{bot}` via trusted command broker\n"
        f"- Branch: `{req.branch}`\n"
        f"- Base: `{req.base_sha}`\n"
        "- Intended paths:\n"
        + "\n".join(f"  - `{file.path}`" for file in req.files)
        + "\n- Coordination: validated against current open PRs\n"
        "- Start time: this comment timestamp is authoritative\n\n" + provenance
    )


def _find_claim_provenance(gh: GH, req: Request) -> dict[str, Any]:
    expected = _claim_provenance(req)
    matches_found: list[dict[str, Any]] = []
    bot = get_bot_name()
    for comment in gh.pages(f"/issues/{req.issue}/comments"):
        if not isinstance(comment, dict):
            continue
        if comment.get("user", {}).get("login") != bot:
            continue
        body = str(comment.get("body") or "")
        if not body.startswith("BOT CLAIM"):
            continue
        record = _decode_record(body, PROVENANCE_PREFIX, PROVENANCE_SUFFIX)
        if record is not None and record == expected:
            matches_found.append(record)
    if len(matches_found) != 1:
        raise BrokerError("Canonical claim provenance is missing or ambiguous")
    return matches_found[0]


def _advance_ref_idempotent(gh: GH, branch: str, new_sha: str) -> None:
    path = "/git/refs/heads/" + urllib.parse.quote(branch, safe="/")
    try:
        gh.patch(path, {"sha": new_sha, "force": False})
    except BrokerError:
        if gh.branch_sha(branch) == new_sha:
            return
        raise
    if gh.branch_sha(branch) != new_sha:
        raise BrokerError("Branch ref did not advance to the expected commit")


def _ensure_reviewer(gh: GH, pr_number: int) -> None:
    owner = get_owner()
    gh.post(f"/pulls/{pr_number}/requested_reviewers", {"reviewers": [owner]})
    reviewers = gh.get(f"/pulls/{pr_number}/requested_reviewers")
    users = {
        user.get("login")
        for user in reviewers.get("users", [])
        if isinstance(user, dict)
    }
    if owner not in users:
        raise BrokerError("Reviewer request verification failed")


def _create_initial_commit(gh: GH, req: Request) -> str:
    base = gh.get(f"/git/commits/{req.base_sha}")
    try:
        base_tree = base["tree"]["sha"]
    except (KeyError, TypeError) as exc:
        raise BrokerError("Malformed base commit") from exc
    tree = gh.post(
        "/git/trees",
        {
            "base_tree": base_tree,
            "tree": [
                {"path": file.path, "mode": file.mode, "type": "blob", "sha": file.sha}
                for file in req.files
            ],
        },
    )
    identity = {"name": get_bot_name(), "email": get_bot_email()}
    commit = gh.post(
        "/git/commits",
        {
            "message": req.message,
            "tree": tree["sha"],
            "parents": [req.base_sha],
            "author": identity,
            "committer": identity,
        },
    )
    sha = str(commit.get("sha") or "")
    if not SHA_RE.fullmatch(sha):
        raise BrokerError("GitHub returned malformed commit SHA")
    return sha


def _create_initial_pr(gh: GH, req: Request) -> dict[str, Any]:
    pr = gh.post(
        "/pulls",
        {
            "title": req.title,
            "head": req.branch,
            "base": "main",
            "body": req.body,
            "maintainer_can_modify": True,
        },
    )
    number = int(pr["number"])
    _ensure_reviewer(gh, number)
    return pr


def mutate(gh: GH, req: Request, materialized: dict[str, Any]) -> tuple[int, str]:
    verify_comment(gh, req)
    validate_remote(gh, req, verify_blobs=False)
    recreate_blobs(gh, req, materialized)
    validate_remote(gh, req, verify_blobs=False)
    gh.post("/git/refs", {"ref": f"refs/heads/{req.branch}", "sha": req.base_sha})
    gh.post(f"/issues/{req.issue}/comments", {"body": _claim_body(req)})
    try:
        commit_sha = _create_initial_commit(gh, req)
        _advance_ref_idempotent(gh, req.branch, commit_sha)
        pr = _create_initial_pr(gh, req)
        number = int(pr["number"])
    except Exception as exc:
        with contextlib.suppress(Exception):
            gh.post(
                f"/issues/{req.issue}/comments",
                {
                    "body": (
                        "BOT BROKER FAILURE\n\n"
                        f"`{req.branch}` remains claimed for reconciliation. "
                        f"Failure class: `{type(exc).__name__}`."
                    )
                },
            )
        raise
    owner = get_owner()
    gh.post(
        f"/issues/{req.issue}/comments",
        {
            "body": (
                "BOT BROKER SUCCESS\n\n"
                f"- Branch: `{req.branch}`\n"
                f"- Commit: `{commit_sha}`\n"
                f"- Pull request: #{number}\n"
                f"- Reviewer requested: `{owner}`"
            )
        },
    )
    return number, str(pr["html_url"])


def _original_request_for_resume(gh: GH, cmd: V2Command) -> Request:
    issue_number = int(cmd.payload["issue"])
    original_id = int(cmd.payload["original_comment_id"])
    comment = gh.get(f"/issues/comments/{original_id}")
    if not isinstance(comment, dict):
        raise BrokerError("Original source comment is missing")
    body = str(comment.get("body") or "")
    if _body_digest(body) != cmd.payload["original_comment_sha256"]:
        raise BrokerError("Original source comment digest mismatch")
    issue = _open_issue(gh, issue_number)
    original = from_event({"issue": issue, "comment": comment})
    if not isinstance(original, Request):
        raise BrokerError("Resume source must be an initial work.create request")
    if request_sha256(original) != cmd.payload["request_sha256"]:
        raise BrokerError("Original request digest mismatch")
    return original


def _resume_open_prs(gh: GH, req: Request) -> list[dict[str, Any]]:
    return [
        pr
        for pr in gh.pages("/pulls?state=open")
        if isinstance(pr, dict) and str(pr.get("head", {}).get("ref", "")) == req.branch
    ]


def _validate_resumed_head(gh: GH, req: Request, head_sha: str) -> None:
    compare = gh.get(f"/compare/{req.base_sha}...{head_sha}")
    if not isinstance(compare, dict) or int(compare.get("ahead_by", -1)) != 1:
        raise BrokerError(
            "Partial branch head is not exactly one commit above the requested base"
        )
    commits = compare.get("commits") or []
    if len(commits) != 1:
        raise BrokerError("Partial branch history is ambiguous")
    commit = commits[0]
    if str(commit.get("sha") or "") != head_sha:
        raise BrokerError("Partial branch commit mismatch")
    detail = commit.get("commit") or {}
    if str(detail.get("message") or "") != req.message:
        raise BrokerError(
            "Partial branch commit message does not match original request"
        )
    for role in ("author", "committer"):
        identity = detail.get(role) or {}
        if (
            identity.get("name") != get_bot_name()
            or identity.get("email") != get_bot_email()
        ):
            raise BrokerError("Partial branch commit identity is not the broker bot")
    rows = compare.get("files") or []
    observed = {str(row.get("filename")): row for row in rows if isinstance(row, dict)}
    if set(observed) != req.paths:
        raise BrokerError("Partial branch changed paths do not match original request")
    for file in req.files:
        row = observed[file.path]
        status = str(row.get("status") or "")
        if file.sha is None:
            if status != "removed":
                raise BrokerError(
                    f"Expected deletion was not preserved for {file.path}"
                )
        elif row.get("sha") != file.sha:
            raise BrokerError(
                f"Partial branch blob does not match original request for {file.path}"
            )


def validate_resume(
    gh: GH,
    cmd: V2Command,
) -> tuple[Request, str, list[dict[str, Any]]]:
    if cmd.operation != "work.resume":
        raise BrokerError("Not a work.resume operation")
    req = _original_request_for_resume(gh, cmd)
    current_main = gh.main_sha()
    if current_main != req.base_sha:
        ancestry = gh.get(f"/compare/{req.base_sha}...{current_main}")
        if (
            not isinstance(ancestry, dict)
            or str(ancestry.get("status") or "") not in {"ahead", "identical"}
            or int(ancestry.get("behind_by", -1)) != 0
        ):
            raise BrokerError(
                "Current main no longer descends from the original requested base"
            )
    _find_claim_provenance(gh, req)
    head = gh.branch_sha(req.branch)
    expected = str(cmd.payload["expected_head_sha"])
    if head != expected:
        raise BrokerError("Resume expected_head_sha does not match canonical branch")
    prs = _resume_open_prs(gh, req)
    if len(prs) > 1:
        raise BrokerError("Multiple open PRs exist for the partial canonical branch")
    exclude = int(prs[0]["number"]) if prs else None
    _validate_scope_and_collisions(gh, req.issue, req.paths, exclude_pr=exclude)
    if head == req.base_sha:
        if prs:
            raise BrokerError(
                "PR exists while canonical branch is still at requested base"
            )
        return req, "at-base", prs
    _validate_resumed_head(gh, req, head)
    if prs and not _pr_maps_issue(prs[0], req.issue, req.branch):
        raise BrokerError("Existing partial PR does not match the original request")
    if prs:
        pr = prs[0]
        if (
            str(pr.get("title") or "") != req.title
            or str(pr.get("body") or "") != req.body
        ):
            raise BrokerError(
                "Existing partial PR metadata does not match original request"
            )
        return req, "pr-exists", prs
    return req, "commit-only", prs


def mutate_resume(
    gh: GH,
    cmd: V2Command,
    materialized: dict[str, Any],
) -> tuple[int, str]:
    verify_comment(gh, cmd)
    req, state, prs = validate_resume(gh, cmd)
    if state == "at-base":
        recreate_blobs(gh, req, materialized)
        req2, state2, _ = validate_resume(gh, cmd)
        if req2 != req or state2 != "at-base":
            raise BrokerError("Resume state changed before branch advancement")
        commit_sha = _create_initial_commit(gh, req)
        _advance_ref_idempotent(gh, req.branch, commit_sha)
        if gh.branch_sha(req.branch) != commit_sha:
            raise BrokerError("Resume branch did not reach the expected commit")
        _validate_resumed_head(gh, req, commit_sha)
        current_prs = _resume_open_prs(gh, req)
        if len(current_prs) > 1:
            raise BrokerError("Multiple PRs appeared during resume")
        if current_prs and not _pr_maps_issue(current_prs[0], req.issue, req.branch):
            raise BrokerError("Unexpected PR appeared during resume")
        exclude_pr = int(current_prs[0]["number"]) if current_prs else None
        _validate_scope_and_collisions(gh, req.issue, req.paths, exclude_pr=exclude_pr)
        if current_prs:
            pr = current_prs[0]
            if (
                str(pr.get("title") or "") != req.title
                or str(pr.get("body") or "") != req.body
            ):
                raise BrokerError("Unexpected PR metadata appeared during resume")
            _ensure_reviewer(gh, int(pr["number"]))
        else:
            pr = _create_initial_pr(gh, req)
    elif state == "commit-only":
        req2, state2, _ = validate_resume(gh, cmd)
        if req2 != req or state2 != "commit-only":
            raise BrokerError("Resume state changed before PR creation")
        pr = _create_initial_pr(gh, req)
    else:
        pr = prs[0]
        _ensure_reviewer(gh, int(pr["number"]))
    number = int(pr["number"])
    gh.post(
        f"/issues/{req.issue}/comments",
        {
            "body": (
                "BOT BROKER RESUME SUCCESS\n\n"
                f"- Branch: `{req.branch}`\n"
                f"- Pull request: #{number}\n"
                f"- Original request: `{request_sha256(req)}`"
            )
        },
    )
    return number, str(pr["html_url"])


def mutate_planning(gh: GH, cmd: V2Command) -> str:
    verify_comment(gh, cmd)
    validate_planning(gh, cmd)
    payload = cmd.payload
    if cmd.operation == "plan.create_milestone":
        request: dict[str, Any] = {"title": payload["title"]}
        if "description" in payload:
            request["description"] = payload["description"]
        if "due_on" in payload:
            request["due_on"] = payload["due_on"]
        row = gh.post("/milestones", request)
        result = f"milestone #{int(row['number'])} `{row['title']}`"
    elif cmd.operation == "plan.create_issue":
        request = {"title": payload["title"], "body": payload["body"]}
        if "milestone" in payload:
            request["milestone"] = int(payload["milestone"])
        row = gh.post("/issues", request)
        result = f"issue #{int(row['number'])}"
    elif cmd.operation == "plan.update_issue":
        target = int(payload["target_issue"])
        request = {}
        if "title" in payload:
            request["title"] = payload["title"]
        if "body" in payload:
            request["body"] = payload["body"]
        row = gh.patch(f"/issues/{target}", request)
        if row.get("state") != "open":
            raise BrokerError("Planning update unexpectedly changed issue state")
        result = f"issue #{target} metadata"
    elif cmd.operation == "plan.assign_milestone":
        target = int(payload["target_issue"])
        milestone = int(payload["milestone"])
        row = gh.patch(f"/issues/{target}", {"milestone": milestone})
        assigned = row.get("milestone") or {}
        if int(assigned.get("number", 0)) != milestone:
            raise BrokerError("Milestone assignment verification failed")
        result = f"issue #{target} -> milestone #{milestone}"
    else:
        raise BrokerError("Not a planning mutation")
    planning_num = get_planning_issue()
    if planning_num is None:
        raise BrokerError("Planning commands are not configured for this repository")
    gh.post(
        f"/issues/{planning_num}/comments",
        {
            "body": f"BOT BROKER SUCCESS\n\n- Operation: `{cmd.operation}`\n- Result: {result}"
        },
    )
    return result


def _work_update_commit(gh: GH, cmd: V2Command, files: tuple[File, ...]) -> str:
    expected_head = str(cmd.payload["expected_head_sha"])
    base = gh.get(f"/git/commits/{expected_head}")
    try:
        base_tree = base["tree"]["sha"]
    except (KeyError, TypeError) as exc:
        raise BrokerError("Malformed work.update base commit") from exc
    tree = gh.post(
        "/git/trees",
        {
            "base_tree": base_tree,
            "tree": [
                {"path": file.path, "mode": file.mode, "type": "blob", "sha": file.sha}
                for file in files
            ],
        },
    )
    identity = {"name": get_bot_name(), "email": get_bot_email()}
    commit = gh.post(
        "/git/commits",
        {
            "message": cmd.payload["commit_message"],
            "tree": tree["sha"],
            "parents": [expected_head],
            "author": identity,
            "committer": identity,
        },
    )
    sha = str(commit.get("sha") or "")
    if not SHA_RE.fullmatch(sha):
        raise BrokerError("GitHub returned malformed work.update commit SHA")
    return sha


def mutate_work_update(
    gh: GH,
    cmd: V2Command,
    materialized: dict[str, Any],
) -> tuple[str, int]:
    verify_comment(gh, cmd)
    _, pr, files = validate_work_update(gh, cmd, verify_blobs=False)
    recreate_file_set(gh, files, materialized)
    _, pr, files = validate_work_update(gh, cmd, verify_blobs=False)
    issue_number = int(cmd.payload["issue"])
    branch = branch_for_issue(issue_number)
    commit_sha = _work_update_commit(gh, cmd, files)
    _advance_ref_idempotent(gh, branch, commit_sha)
    pr_number = int(pr["number"])
    if "pr" in cmd.payload:
        metadata = cmd.payload["pr"]
        updated = gh.patch(
            f"/pulls/{pr_number}",
            {"title": metadata["title"], "body": metadata["body"]},
        )
        if (
            str(updated.get("title") or "") != metadata["title"]
            or str(updated.get("body") or "") != metadata["body"]
        ):
            raise BrokerError("PR metadata update verification failed")
    _ensure_reviewer(gh, pr_number)
    gh.post(
        f"/issues/{issue_number}/comments",
        {
            "body": (
                "BOT BROKER UPDATE SUCCESS\n\n"
                f"- Branch: `{branch}`\n"
                f"- Commit: `{commit_sha}`\n"
                f"- Pull request: #{pr_number}"
            )
        },
    )
    return commit_sha, pr_number


def _preflight_command(gh: GH, cmd: Command) -> dict[str, Any]:
    if isinstance(cmd, Request):
        validate_remote(gh, cmd, verify_blobs=False)
        return {"materialized_blobs": materialize_blobs(gh, cmd)}
    if cmd.operation.startswith("plan."):
        validate_planning(gh, cmd)
        return {"materialized_blobs": {}}
    if cmd.operation == "work.update":
        _, _, files = validate_work_update(gh, cmd, verify_blobs=False)
        return {"materialized_blobs": materialize_file_set(gh, files)}
    if cmd.operation == "work.resume":
        req, state, _ = validate_resume(gh, cmd)
        materialized = materialize_blobs(gh, req) if state == "at-base" else {}
        return {"materialized_blobs": materialized, "resume_state": state}
    raise BrokerError("Unsupported command")


def _saved_command(cmd: Command, extra: dict[str, Any]) -> dict[str, Any]:
    if isinstance(cmd, Request):
        saved = {
            "kind": "work.create.v1",
            "payload": _request_payload(cmd),
            "source_issue": cmd.issue,
            "source_comment_id": cmd.comment_id,
            "source_comment_sha256": cmd.comment_digest,
        }
    else:
        saved = {
            "kind": "v2",
            "payload": cmd.payload,
            "source_issue": cmd.source_issue,
            "source_comment_id": cmd.comment_id,
            "source_comment_sha256": cmd.comment_digest,
        }
    saved.update(extra)
    return saved


def _command_from_saved(data: dict[str, Any]) -> tuple[Command, dict[str, Any]]:
    if not isinstance(data, dict):
        raise BrokerError("Saved broker request must be an object")
    kind = data.get("kind")
    payload = data.get("payload")
    source_issue = _positive_int(data.get("source_issue"), "source_issue")
    comment_id = _positive_int(data.get("source_comment_id"), "source_comment_id")
    digest = _sha256_value(data.get("source_comment_sha256"), "source_comment_sha256")
    materialized = data.get("materialized_blobs")
    if not isinstance(materialized, dict):
        raise BrokerError("Saved request lacks materialized blobs")
    if kind == "work.create.v1":
        if not isinstance(payload, dict):
            raise BrokerError("Malformed saved work.create payload")
        cmd: Command = parse_payload(payload, comment_id, digest)
        if not isinstance(cmd, Request) or cmd.issue != source_issue:
            raise BrokerError("Saved work.create source issue mismatch")
    elif kind == "v2":
        if not isinstance(payload, dict):
            raise BrokerError("Malformed saved v2 payload")
        cmd = _parse_v2(payload, source_issue, comment_id, digest)
    else:
        raise BrokerError("Unknown saved broker request kind")
    return cmd, materialized


def execute_command(gh: GH, cmd: Command, materialized: dict[str, Any]) -> str:
    if isinstance(cmd, Request):
        number, url = mutate(gh, cmd, materialized)
        return f"Created PR #{number}: {url}"
    if cmd.operation.startswith("plan."):
        result = mutate_planning(gh, cmd)
        return f"Completed {cmd.operation}: {result}"
    if cmd.operation == "work.update":
        sha, number = mutate_work_update(gh, cmd, materialized)
        return f"Updated PR #{number} with commit {sha}"
    if cmd.operation == "work.resume":
        number, url = mutate_resume(gh, cmd, materialized)
        return f"Resumed PR #{number}: {url}"
    raise BrokerError("Unsupported command")


def request_from_saved(data: dict[str, Any]) -> Request:
    digest = str(data.pop("source_comment_sha256"))
    comment_id = int(data.pop("source_comment_id"))
    return parse_payload(data, comment_id, digest)


def cmd_validate(args: argparse.Namespace) -> int:
    repo = get_repo()
    if os.environ.get("GITHUB_REPOSITORY", repo) != repo:
        raise BrokerError("Repository mismatch")
    with open(args.event, encoding="utf-8") as handle:
        event = json.load(handle)
    cmd = from_event(event)
    gh = GH(os.environ.get("GITHUB_TOKEN", ""))
    extra = _preflight_command(gh, cmd)
    saved = _saved_command(cmd, extra)
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(saved, handle, sort_keys=True, separators=(",", ":"))
        handle.write("\n")
    operation = "work.create" if isinstance(cmd, Request) else cmd.operation
    print(
        f"Validated broker operation {operation} from issue #{event['issue']['number']}"
    )
    return 0


def cmd_execute(args: argparse.Namespace) -> int:
    repo = get_repo()
    if os.environ.get("GITHUB_REPOSITORY", repo) != repo:
        raise BrokerError("Repository mismatch")
    with open(args.request, encoding="utf-8") as handle:
        data = json.load(handle)
    cmd, materialized = _command_from_saved(data)
    result = execute_command(
        GH(os.environ.get("AGENT_GITHUB_TOKEN", "")), cmd, materialized
    )
    print(result)
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("validate")
    a.add_argument("--event", required=True)
    a.add_argument("--output", required=True)
    a.set_defaults(fn=cmd_validate)
    a = sub.add_parser("execute")
    a.add_argument("--request", required=True)
    a.set_defaults(fn=cmd_execute)
    args = p.parse_args()
    try:
        return args.fn(args)
    except BrokerError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: broker failed closed ({type(e).__name__})", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
