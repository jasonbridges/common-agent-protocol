# Readability and Design

Read this with the [code-quality index](README.md) and the component's accepted architecture. The aim is code whose purpose, dependencies, state changes, and failure behavior another engineer can explain from the source.

## Make intent visible

Name values for their domain and units. `retry_delay_seconds`, `lease_owner_id`, and `available_memory_bytes` convey contracts that `value`, `data`, and `limit` often conceal. Short names are useful in a small, obvious context; long names do not compensate for an unclear responsibility.

Keep data shapes explicit at boundaries. Prefer named records and domain states over positional tuples, unrelated boolean flags, or an unvalidated dictionary passed through many layers. Distinguish missing, empty, invalid, stale, and unauthorized data when they lead to different behavior.

Comments should preserve information the code cannot express well: a protocol invariant, a compatibility constraint, a concurrency assumption, a hardware register quirk, or the reason for a workaround. Public APIs should explain inputs, outputs, ownership, and failures. Update comments when the behavior changes.

## Keep the control flow easy to follow

Use straightforward branches for decisions with different effects. Guard clauses can make preconditions clear, provided they preserve required cleanup and error reporting. Extract a named predicate when it explains a domain decision, rather than merely moving a difficult expression elsewhere.

Avoid dense expressions that mix filtering, mutation, I/O, and error handling. Keep the normal path and the failure path visible. A state transition should make its precondition, mutation, and externally visible result easy to find.

There is no universal maximum function length, nesting count, or number of classes. Split code when responsibilities or reasons to change differ, or when the reader must track too much state. Keep closely related logic together when splitting it would add indirection without explaining anything.

## Choose useful module boundaries

Separate pure decision logic from side-effecting adapters (hardware, network, filesystem, process) and keep CLI/entrypoint wrappers thin:

- Put policy, wire codecs, and state transitions where they can be tested with ordinary values.
- Put hardware registers, network, filesystem, process, clock, and credential access behind explicit boundaries. Inject the dependency that varies; avoid a global service registry.
- Give a module one cohesive responsibility and a small, understandable public interface. Keep internal helpers private unless a real consumer needs them.
- Extract a shared abstraction when its contract is stable and its consumers agree. Similar-looking code with different trust or failure semantics may need to remain separate.

A new layer, interface, crate, or dependency should have a concrete reason: a responsibility boundary, independent authority, a useful test seam, actual reuse, or measured build/runtime benefit. Avoid speculative extension points and generic frameworks for a single known use case.

## Make failures and resource ownership explicit

Validate external data before it becomes trusted domain state. Type annotations and successful parsing do not establish authorization, valid ranges, or freshness. Defaults must follow the component contract; an unavailable security decision must not silently become permission to continue.

Handle errors where there is enough context to recover or translate them. Preserve causes, cancellation, and meaningful status. Do not log and suppress an error only to return a success-shaped result. Diagnostics should identify the operation and safe context without exposing credentials or raw sensitive payloads.

Every file, process, task, temporary directory, subscription, and lock needs a clear owner and lifetime. On failure or cancellation, make cleanup behavior observable. For durable state, follow the component's atomicity, permissions, recovery, and versioning contract; an atomic rename alone does not prove all of those properties.

## Keep concurrency and recovery understandable

Identify who owns mutable state and how other participants communicate with that owner. Bound queues, retries, concurrency, and work duration according to the component's requirements. State how workers stop, which task joins them, and what happens to partially completed work.

Avoid holding a lock across slow I/O unless the design requires it and the scope is justified. Make lock ordering and state transitions explicit. Duplicate calls, timeouts after a possible write, and restart recovery need defined semantics; retrying an uncertain side effect is not automatically safe.

## Test behavior and preserve useful evidence

Tests should prove externally meaningful results or a specific invariant. Include failure, boundary, cancellation, and recovery cases where the changed behavior depends on them. A regression test should fail for the defect it protects against.

Use deterministic fixtures and synchronization. Inject clocks or transports where needed, rather than relying on arbitrary sleeps or a live service. Keep test data minimal enough that the relevant case is visible. Avoid copying the implementation into the test or asserting incidental helper calls instead of outcomes.

Choose validation proportional to the actual change and the repository's required gates. Straightforward prose does not need a new test that checks its wording; links and examples still need verification. Preserve the distinction between unit evidence, artifact/package evidence, and live-environment/hardware qualification. Record missing tooling and skipped checks accurately.

## Treat build speed as an engineering property

Keep dependency and input closures narrow enough that a small change invalidates only relevant work. Use the component's authoritative build graph and pinned toolchain. Avoid duplicate build paths and re-compiling an artifact during packaging when the canonical build already produced it.

Measure a suspected bottleneck before adding caches, parallelism, code generation, or another module boundary. Explain the workload, cold/warm state, relevant source change, elapsed time, and correctness checks. Distinguish a faster local edit from a faster clean build or CI queue; they answer different questions.
