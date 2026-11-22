# Failure, Concurrency, and Recovery

Use this with [readability guidance](readability.md), [contracts and boundaries](contracts-and-boundaries.md), and the component's accepted state, security, and recovery design. It explains how to make partial failure reviewable across languages. Existing contracts control retry budgets, authorization, durable transitions, and operational recovery.

## Identify the operation and its owner

Describe an operation by the effect it owns, rather than by one function call. A timeout may end a caller's wait while a remote worker continues. An exception may occur after a write. A successful write may still have uncompleted cleanup. Represent those distinctions when they affect the next safe action.

| Responsibility | Questions the implementation must answer |
| --- | --- |
| Admission | Who authorizes this exact effect, and how long is that authority valid? |
| State ownership | Which process/task/core owns mutable state, and what synchronizes competing writers? |
| Operation identity | How are a duplicate request and a conflicting request distinguished? |
| Commit | What single observation or atomic operation establishes the effect? |
| Cancellation | Which work stops, who waits for it, and what may already have committed? |
| Recovery | What evidence survives restart or power cut, and who may reconcile an uncertain outcome? |
| Cleanup | Who releases each resource, and what establishes completed cleanup? |

Prefer synchronous composition where callers can own the work. When concurrency is useful, give each task an explicit lifetime, error path, cancellation signal, and join/cleanup owner. Bound queues and active work as well as individual calls. Document lock ordering and avoid slow I/O under a lock unless the design requires that serialization. A local lock does not coordinate other processes, cores, or hosts.

## Classify failure before choosing a retry

| Observed outcome | Reasonable next step, subject to the component contract |
| --- | --- |
| Invalid input or denied authority | Return the stable refusal; another identical attempt cannot repair it |
| Transient failure before any effect is possible | Retry only within the permitted attempt/time budget |
| Effect may have happened; reply or persistence failed | Preserve uncertainty and reconcile the original operation |
| Effect is proven committed | Return or recover that result; do not create a replacement operation |
| Cleanup failed after a known effect | Report both the effect and cleanup debt; continue only the permitted cleanup path |
| State is corrupt, conflicting, or unverifiable | Follow the accepted blocking/containment and recovery rule |

Retry policy belongs at the layer that understands the operation. Nested retry loops can multiply attempts and exceed the intended total deadline. Specify the total time and attempt budget, backoff, and any jitter through the component's configuration.

An idempotency key or monotonic counter is useful only if the receiving service enforces its binding to the full request and retains it across restarts for the required lifetime. Reusing a key or counter with different data must not silently execute a different operation.

## Worked example: publication succeeded but its reply was lost

Suppose a component publishes one immutable manifest under a stable operation ID. This illustrative design assumes the destination provides atomic creation that cannot replace an existing object, and a trusted read of its operation ID and digest. The same ID with the same bytes is a duplicate; the same ID with different bytes is a conflict.

Before sending, the owner records the operation ID, request digest, destination, and state through the component's required durable mechanism. The destination creates the manifest, but the connection drops before the owner receives a reply. The owner records an uncertain result and reads that same operation back. It does not choose a new ID, overwrite the destination, or claim publication failed.

| State/evidence | Permitted transition in this example | What remains forbidden |
| --- | --- | --- |
| Intent is durable; no request sent | Begin the authorized conditional publication | Send after intent persistence failed |
| Send began; outcome unknown | Read and reconcile the exact operation | Treat timeout as proof that no write occurred |
| Destination proves matching ID and digest | Record committed result; perform owned cleanup | Publish again under a fresh ID |
| Destination proves conflicting content | Preserve conflict and block for the documented resolution | Overwrite or relabel the existing operation |
| Read fails or an absent result is not authoritative | Remain uncertain | Convert absence of evidence into a safe retry |
| Required destination semantics prove retry cannot duplicate/change the effect | Retry the same ID and bytes within authority and budget | Extend authority or change payload to make progress |
| Commit known; cleanup or local result save fails | Retain result and unresolved obligations; reconcile on restart | Report clean completion or erase the recovery record |
| Commit and required cleanup are verified and recorded | Complete the operation | Discard evidence earlier than the retention contract allows |

## Make cancellation and shutdown a complete path

- Propagate the caller's cancellation/deadline to owned work. If cleanup needs a separate bounded lifetime, make that policy and its owner explicit; do not detach ordinary work by silently replacing its context.
- Decide how cancellation competes with commit. Report a known committed effect truthfully even if the caller stopped waiting. A cancellation result alone must not imply that a remote mutation was rolled back.
- Stop admitting work before draining it. Account for queued work, active tasks, subprocesses, open files/sockets, locks, and subscriptions according to their owners. Sending a signal or cancelling a future is not proof of termination.
- Preserve the original operation error and any cleanup error. Do not hide a failed teardown behind a successful operation result or an unconditional zero exit status. Diagnostics must remain bounded and free of credentials.

## Preserve recovery across crash, rollback, and restart

Define which transitions require durable evidence before an external effect. Use the component's proven storage mechanism and concurrency preconditions. Atomic replacement, durable persistence, correct permissions, and authenticated state are separate properties. A rename alone establishes none of the others; on disk/flash, dual-copy CRC'd records or `fsync`/parent-dir flush contracts must be honored explicitly.

On restart, distinguish incomplete work, proven completion, and corrupt or unknown state. Preserve unresolved records through retention and rollback. Age, an empty process list, or a missing response is not by itself authority to release a reservation. The accepted design decides when a lease expires and what fencing or reconciliation prevents an old worker from acting afterward.

Multiple layers must not independently start automatic rollback without a clear single owner. Restore order, pre-existing versus absent objects, quiescence, and failed completion hooks belong to that transaction contract. A source revert does not restore deployed or flashed state.

## Test the transitions that can lose information

Use injected clocks, controlled transports, and explicit synchronization points. Exercise the real adapter or disposable integration environment where its atomicity, process lifetime, or filesystem behavior matters. Avoid arbitrary sleeps as proof that a race occurred. Add cases proportional to the changed contract:

| Fault or interleaving | Evidence to assert |
| --- | --- |
| Intent persistence fails | No external mutation starts |
| Remote commit followed by lost reply | Original result is reconciled; no replacement operation |
| Duplicate ID with identical/different payload | Specified duplicate result/conflict; no uncontrolled mutation |
| Cancellation immediately before and after commit | Correct effect classification, cleanup, and returned outcome |
| Two owners contend or a stale worker finishes | Actual synchronization/fencing rule prevents forbidden publication |
| Restart at each durable transition | Same obligations survive; no fabricated clean state |
| Cleanup, rollback, or result persistence fails | Failure/debt remains visible and prevents an unjustified completion |
| Retry budget expires | Bounded attempts/time; uncertainty and required cleanup remain accounted for |

## Review and validation

- Can each side effect be tied to one owner, operation identity, and authority?
- Is retry justified by proven destination semantics or reconciled prior outcome?
- Are commit, cancellation, cleanup, and restart states explicit and tested?
- Does the implementation preserve unresolved evidence and reject conflicting state?
- Do diagnostics distinguish known effects, unknown outcomes, and cleanup debt?

## Further reading

- [Amazon: timeouts, retries, and backoff with jitter](https://aws.amazon.com/builders-library/timeouts-retries-and-backoff-with-jitter/): uncertain side effects, retry amplification across layers, and bounded backoff.
- [Google SRE: handling overload](https://sre.google/sre-book/handling-overload/): per-request and aggregate retry budgets, and the cost of repeated overload.
