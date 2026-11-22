# Code Quality, Language, and Testing Guides

Use these guides when creating, changing, or reviewing code in any repository that mounts `common-agent-protocol`. They explain how to make changes understandable, testable, and maintainable; the universal operating contract in [`CORE-AGENTS.md`](../../CORE-AGENTS.md) and the consuming repository's local `AGENTS.md` still control ownership, authority, validation, review disposition, and delivery.

## Start here

1. Follow the ordered context loading in [`CORE-AGENTS.md §2`](../../CORE-AGENTS.md#2-mandatory-ordered-context-loading): read the repository's `AGENTS.md`, the task and discussion, relevant designs, accepted ADRs, policies, and dependency state before inspecting the implementation.
2. Read [shared readability and design guidance](readability.md), then the source and behavior guides matching the task below. Read the component's local instructions too.
3. Inspect the consuming repository's committed tool configuration and build targets. Run the applicable checks and report what actually executed.
4. Before review, apply the repository's review playbook (see [`templates/REVIEWERS.md`](../../templates/REVIEWERS.md)). Explain material design choices and validation gaps in the PR description.

## Choose the applicable guide

| Changed source | Guide | Main concerns |
| --- | --- | --- |
| Any language | [Readability and design](readability.md) | Names, control flow, module boundaries, state, tests, performance |
| Rust (`.rs`, crate metadata) | [Rust](rust.md) | Ownership, explicit states, errors, `#![no_std]`/embedded safety, `unsafe`/FFI, Bazel builds |
| C / C++ (`.c`, `.cc`, `.cpp`, `.h`, `.hpp`) | [C and C++](cpp.md) | Pure `core/` vs HAL, spans, RAII, freestanding/embedded alignment & MMIO, bounded waits |
| Python (`.py`) | [Python](python.md) | Imports, typed boundaries, exceptions, resources, package architecture |
| Go (`.go`) | [Go](go.md) | Package APIs, errors, contexts, goroutines, Bazel tests |
| Shell (`.sh`, shell entrypoints and package hooks) | [Shell](shell.md) | Quoting, exit status, interpreter compatibility, cleanup |
| Browser JavaScript, Node tests, TypeScript | [JavaScript and TypeScript](javascript-typescript.md) | Runtime validation, asynchronous work, DOM safety, accessibility |
| `BUILD.bazel`, `MODULE.bazel`, `.bzl`, Bazel configuration | [Bazel and Starlark](bazel-starlark.md) | Declared inputs, useful target boundaries, hermeticity, cache behavior |
| Protocol Buffers (`.proto`) | [Protocol Buffers](protobuf.md) | Field identity, presence, wire compatibility, generated outputs |
| YAML, JSON, workflows, systemd units, Containerfiles | [Configuration and infrastructure](configuration.md) | Semantic validation, precedence, identity, privileges, rollout |

Changes often need more than one guide: a Go RPC change needs the Go and Protobuf guides; an embedded Rust driver change needs Rust, C/C++ (for FFI/HAL parity), and Configuration/Bazel; a runner service change may also need Configuration and Shell. For a language not listed, identify its actual compiler, build, formatter, and component conventions in the consuming repository.

### Choose by changed behavior too

| Task | Guide | Decision it supports |
| --- | --- | --- |
| Add or change behavior, tests, or a regression fix | [Test design](../testing/test-design.md) | Connect an acceptance criterion to observable assertions and relevant evidence |
| Use clocks, transports, fixtures, processes, or concurrent test work | [Test doubles and fixtures](../testing/test-doubles-and-fixtures.md) | Choose real dependencies or bounded fakes, control time, and own cleanup |
| Parse input, expose an API, authorize an action, or read trusted state | [Contracts and boundaries](contracts-and-boundaries.md) | Define valid input, authority, compatibility, and allowed side effects |
| Mutate state, retry, cancel, publish, recover, or coordinate workers | [Failure and recovery](failure-and-recovery.md) | Define uncertain outcomes, replay safety, ownership, and restart behavior |
| Add or change runbooks, recovery procedures, or operational docs | [Operational documentation standard](../operational-documentation-standard.md) | Define health/unsafe evidence, rollback triggers, recovery steps, and evidence states |

Select from the behavior and trust boundaries changed, not just the file extension.

## How to interpret the guidance

- **Repository requirements** come from `CORE-AGENTS.md`, the repository's `AGENTS.md`, accepted ADRs, component contracts, and committed configuration. These guides do not override that authority hierarchy.
- **Design defaults** guide judgment. Departures need an explanation when they affect maintainability, compatibility, testability, or performance. A personal preference is not a new merge requirement.
- **Tool status** is stated separately from advice. A recommended check does not imply that CI runs it, and a passing formatter does not establish readability.

Apply the guidance to new and materially changed code. Keep unrelated cleanup out of a behavioral change. When existing debt cannot be fixed within scope, identify the affected behavior and a focused follow-up; do not widen exemptions or copy a legacy workaround into new code.
