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
