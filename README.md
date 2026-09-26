# Common Agent Protocol (`common-agent-protocol`)

The universal multi-agent operating contract, coordination protocols, and governance standards for autonomous coding agents collaborating across repositories.

## Overview

This repository defines project-agnostic agent operating rules:
- Document authority and architectural conflict resolution
- Mandatory ordered context loading
- Work claiming, atomic branch reservation, and stale claim reclamation
- Scope ownership, path collision detection, and reciprocal coordination exceptions
- Durable GitHub project status updates
- Milestone tracking and issue/PR parity
- Pull request lifecycle and review readiness verification
- Agent identities (`agent-env.sh`) and remote command broker envelopes
- Forbidden shortcuts and safe ambiguity fallbacks
- Break-glass emergency procedures

## Consuming in Downstream Repositories

Downstream repositories include this repository as a git submodule mounted at `.agents/`:

```bash
git submodule add https://github.com/jasonbridges/common-agent-protocol.git .agents
```

The consuming repository's root `AGENTS.md` acts as an entry point:
1. Directs agents to read `.agents/CORE-AGENTS.md`.
2. Declares repository-specific invariants, architecture constraints, and build/validation commands (e.g. Bazel targets, Nix/systemd configs).

## GitHub App Command Broker

This repository provides a generalized GitHub App Command Broker (`scripts/agent-command-broker.py`) allowing remote or local AI agents to submit tasks, create bot-authored commits, open PRs, and advance task state via declarative markdown envelopes without direct repository write credentials or personal access tokens.

### Configuration
Consuming repositories can install `.github/workflows/agent-command-broker.yml` (template available in `templates/workflows/agent-command-broker.yml`) and customize environment variables:
- `AGENT_BROKER_OWNER`: GitHub username or org (defaults to repository owner)
- `AGENT_BOT_NAME`: Committer name (defaults to `jasonbridges-agent[bot]`)
- `AGENT_BOT_EMAIL`: Committer email (defaults to `331491158+jasonbridges-agent[bot]@users.noreply.github.com`)
- `AGENT_BROKER_BRANCH_PATTERN`: Python format string for branch naming (defaults to `work/issue-{issue}`)
- `AGENT_BROKER_BRANCH_RE`: Regex pattern for matching managed branches (defaults to `^work/issue-(\d+)$`)
- `AGENT_BROKER_PLANNING_ISSUE`: Issue number for planning commands (defaults to repo-specific planning issue or disabled when blank/unset)

