# Substantive PR Review Playbook (Template)

This template defines the reusable technical review checklists for automated reviewers and authoring agents. Consuming repositories copy or adapt it to `.github/REVIEWERS.md` and add repository-specific runtime/trust boundary sections.

Both automated and human reviewers should evaluate every pull request against all applicable areas below, in addition to correctness, security, and test coverage. If an area does not apply, record an explicit "not applicable" result and the reason.

---

## 1. Readability, Design, and Maintainability

Apply these checks to the changed behavior and relevant surrounding code (full guidance: `.agents/docs/code-quality/readability.md`):

- **Intent and data:** Names communicate domain meaning and units. Public boundaries identify inputs, outputs, state, and errors. Distinguish missing, invalid, stale, and unauthorized values when they require different behavior.
- **Control flow:** The normal path, preconditions, mutations, and failure paths are understandable. Dense expressions, hidden side effects, or excessive indirection must not obscure a material decision or cleanup requirement.
- **Cohesion and scope:** Keep policy and wire codecs separate from hardware/OS I/O where the component design requires it. Modules and APIs have clear responsibilities. New abstractions and dependencies need a real consumer, boundary, test seam, or measured benefit.
- **Errors and ownership:** Preserve error causes and cancellation. Identify who owns resources and mutable state, how workers stop, and how uncertain effects recover. Bound concurrency, queues, retries, and hardware wait loops according to the contract.
- **Tests and documentation:** Tests verify meaningful behavior and relevant failure cases without copying the implementation or relying on arbitrary sleeps. Comments explain invariants and reasons. Update affected API, build, and recovery guidance.
- **Performance:** Use the authoritative build graph and narrow dependencies. Claims about runtime or build speed need relevant measurements, including cold/warm state.

Require corrections for concrete defects or applicable contract violations and explain the impact. Mark optional style/refactoring advice as optional.

---

## 2. Language-Specific Checks

Apply every relevant row for a mixed-language change. Committed tool configuration and accepted component contracts control versions, compatibility, and enforcement.

| Source | Checks to apply |
| --- | --- |
| Rust (`.agents/docs/code-quality/rust.md`) | Make ownership, domain states, and error paths explicit. Zero `.unwrap()`, `.expect()`, or unchecked indexing on external/wire paths. Keep `unsafe`/FFI/MMIO minimal with `// SAFETY:` invariants. For `#![no_std]`/bare-metal: explicit endian byte codecs, bounded stacks/buffers, and timed-out hardware polls. Use the repository's authoritative build graph (e.g., Bazel `rules_rust`). |
| C / C++ (`.agents/docs/code-quality/cpp.md`) | Keep pure `core/` separate from HAL/OS glue. Use bounded views (`span`/`ByteSpan`), overflow-safe bounds checks, explicit byte-order serialization (no packed-struct casts), `alignas` / strict-align safety for MMU-off DMA/FIFO paths, `volatile` MMIO + memory barriers across cores, bounded hardware poll loops, and wrap-safe 32/64-bit timers. |
| Python (`.agents/docs/code-quality/python.md`) | Use normal package imports, typed boundaries, and focused functions. Avoid runtime `sys.path` mutation, broad import fallbacks, mutable defaults, and hidden import-time I/O. Catch specific expected failures and close resources. Honor project `ruff`/`mypy` config. |
| Go (`.agents/docs/code-quality/go.md`) | Keep package APIs and consumer interfaces small. Preserve contextual errors with `%w` wrapping and semantic inspection. Propagate context, cancellation, and deadlines; account for every goroutine's exit and shared-state synchronization. |
| Shell (`.agents/docs/code-quality/shell.md`) | Honor the declared interpreter, quote expansions, and use argument arrays in Bash. Avoid `eval` and implicit command-string parsing. Check critical exit statuses and preserve primary/cleanup failures; `set -e` is not complete error handling. |
| JavaScript / TypeScript (`.agents/docs/code-quality/javascript-typescript.md`) | Validate external data at runtime, handle rejected/non-2xx requests and stale responses, and cancel/dispose owned work. Render untrusted text safely (`textContent`); preserve accessible loading/error/empty states. |
| Bazel / Starlark (`.agents/docs/code-quality/bazel-starlark.md`) | Use readable targets, explicit dependencies, narrow visibility, and declared inputs/tools/runfiles. Avoid ambient host discovery and undeclared network access. Preserve committed pins and useful cache invalidation. |
| Protocol Buffers (`.agents/docs/code-quality/protobuf.md`) | Preserve field numbers and reserve removed names/numbers. Review presence, enum defaults, binary/JSON compatibility, and generated-code provenance. |
| Configuration / Infrastructure (`.agents/docs/code-quality/configuration.md`) | Validate schemas and semantics, key/override precedence, units, paths, role identities, and permissions. Preserve workflow command boundaries, pinned image digests, least-privilege systemd hardening, and recovery behavior. |

---

## 3. Test Design, Boundaries, and Recovery

Use these self-contained checks with the applicable language row (full guidance: `.agents/docs/testing/test-design.md`):

- **Assertion quality:** Identify the changed contract and the defect each relevant test could detect. Assert observable results and contractual interactions, including prohibited side effects. Expected values must come from the contract; copying the implementation into the test does not provide independent evidence.
- **Regressions and controls:** A regression test should expose the original defect when reproducible. Validators and guards need useful acceptance and rejection controls; an implementation that refuses everything must not appear correct.
- **Deterministic fixtures:** Control clocks, transport responses, randomness, and synchronization where those affect the assertion. Use minimal synthetic fixtures and bounded fakes that still enforce real hardware/protocol constraints (alignment, sizes, persistence). Account for cleanup and temporary files.
- **Input and authority:** State presence, type, range, units, size, freshness, and authorization rules where applicable. Validate before the protected side effect. Rejection tests check that forbidden writes, publication, or privileged calls did not occur.
- **Partial outcomes:** Distinguish failure before mutation from a lost response after possible completion. Justify replay with the component's idempotency or reconciliation contract. Test relevant cancellation, restart, power-cut, and cleanup-failure cases.
- **Evidence selection:** Distinguish unit tests, emulator/QEMU tests, and live-hardware/deployment qualification. Report the exact scope of what ran and what remains unverified on hardware.

---

## 4. Repository-Specific Boundaries (Customize per Repo)

> Consuming repositories should add sections here for their own execution environment, privilege boundaries, binary wire/disk/IPC formats, and hardware-in-the-loop or deployment gates.
