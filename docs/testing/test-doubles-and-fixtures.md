# Test Doubles, Fixtures, and Deterministic Execution

Read this with [test design](test-design.md) and the component's interface contract. Use controlled dependencies to expose a specific behavior while keeping the behavior under test real.

## Choose the smallest useful test boundary

| Dependency or behavior | Useful default | Limit to state explicitly |
| --- | --- | --- |
| Pure calculation or validation | Real functions with ordinary values | Does not establish adapter, hardware, or deployment behavior. |
| Time and retry scheduling | Injected clock and recorded sleep | Does not measure real scheduler latency or hardware timer/WDT behavior. |
| Remote or UART/SPI transport | Scripted responses/errors at the transport boundary | Does not prove physical signal integrity, baud/clock setup, or peer interoperability. |
| File parsing and ordinary file I/O | Real files in a test-owned temporary directory | Does not establish another UID's permissions or power-cut crash durability. |
| Cross-component protocols | In-process co-simulation of both real state machines over fake/in-memory transport | Does not prove interrupt/MMIO register wiring on silicon. |
| Process-wide signals or boot chain | Bounded subprocess or QEMU/emulator smoke test | Does not prove real peripheral silicon behavior. |

A stub supplies a response; a spy records an interaction; a fake implements a small useful part of an interface. Keep the real parser, policy, serializer, and decision logic in the path when they are the subject.

Make unexpected calls fail clearly rather than silently returning success. Scripted queues should expose unexpected extra attempts. Enforce real hardware constraints in fakes where bugs hide (for example, strict alignment checks, bounded buffer sizes, or non-volatile counter persistence).

## Worked example: time without waiting

```python
import math


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        if not math.isfinite(seconds) or seconds < 0:
            raise ValueError("sleep must be finite and nonnegative")
        self.sleeps.append(seconds)
        self.now += seconds
```

Use one clock domain for a deadline and the code that compares it. Keep policy tests using virtual time paired with separate adapter/emulator tests for real timeout behavior when that boundary changes.

## Keep fixtures small and owned

Build only the state needed to make the invariant visible. Give each test fresh mutable data; reusing a shared mutable fixture couples tests.

Use synthetic identifiers and data. Keep credentials, session values, and production data out of fixtures. Keep fixtures and helper imports in the build system's declared test inputs/runfiles rather than reading from an ambient checkout or home directory.

## Register cleanup when acquisition succeeds

Use context managers, RAII guards, or `addCleanup` tied to each acquired resource so a later setup failure still releases earlier resources. Preserve setup/test errors and cleanup errors instead of suppressing teardown failures.

## Synchronize on events, not guesses

Use events, barriers, channels, or a controlled fake boundary to establish that a worker reached the state relevant to the assertion. A fixed `sleep` does not prove ordering. Keep waits bounded and check their result so a missed signal produces a clear failure.
