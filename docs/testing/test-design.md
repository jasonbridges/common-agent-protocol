# Designing Tests That Establish Behavior

Use this guide to turn a change's acceptance criteria into useful tests. The consuming repository's `AGENTS.md` and CI/quality-gate docs determine required evidence levels and commands.

## Start with the contract

Before choosing a test framework, identify the changed decision or effect. For each acceptance criterion, write down:

1. The observable result or invariant, including prohibited effects.
2. The valid, boundary, and failure inputs that distinguish correct behavior.
3. The assertion that would detect the relevant defect.
4. The real components and external boundaries the test exercises.
5. The required evidence level and any separate artifact, emulator, or live-hardware verification.

Classify by behavior and trust boundary. A pure helper test cannot qualify the deployment or hardware driver that calls it.

## Worked example: make a retention decision visible

Suppose a retention planner enforces a 10 MiB quota with an 80% high watermark, 70% low watermark, and 7-day success TTL across three 3 MiB bundles aged 5, 3, and 1 day:

```python
now, day, mib = 1_700_000_000.0, 86_400.0, 1024 * 1024
# ... build policy and 3 bundles ...
plan = calculate_reap_plan(bundles, policy, now)

assert [bundle.path for bundle in plan.watermark_bundles] == ["old-success"]
assert plan.remaining_bytes == 6 * mib
assert plan.expired_bundles == []
assert plan.emergency_bundles == []
```

The explicit expected path catches reversed ordering or excessive pruning; the byte assertion catches incorrect accounting. Checking only that a plan exists, or computing expected paths with the planner's own sorting/filtering helpers, would leave those mistakes undetected.

Select boundary cases from the actual contract:

| Case | Question to establish |
| --- | --- |
| Exactly at a threshold and immediately across it | Is the boundary inclusive or exclusive as specified? |
| Empty input and one eligible item | Are minimum cases handled without special accidental behavior? |
| Protected items mixed with eligible items | Does pruning preserve required evidence? |
| Equal timestamps / wraparound counters | Does the test respect tie-breaking and 32-bit/64-bit modular wraparound? |
| Multi-step interaction | Is state accounted for once across transitions? |

## Write assertions that survive a sound refactor

Name tests for the behavior or failure mode. Keep setup, action, and assertions visible; a helper should remove irrelevant repetition without hiding the inputs that make a case special. Give parameterized cases meaningful names and keep unrelated scenarios separate when they need different setup or explanations.

Assert returned values, durable state, emitted protocol data, or prohibited effects. An interaction assertion is useful when the interaction is itself a contract (no write before authorization, state persisted before reboot/ACK, bounded retry count). Incidental helper calls and private layout are poor substitutes for those outcomes. See [test doubles and fixtures](test-doubles-and-fixtures.md).

For a regression, verify the test fails on the unpatched defect (for the intended assertion, not a setup error) and passes once fixed. For validators, pair rejection cases with accepted controls so rejecting every input cannot pass.

## Choose additional techniques for the risk

| Technique | Useful when | Keep the evidence meaningful |
| --- | --- | --- |
| Property or invariant checks | Many inputs share a stable relationship | Derive the property from the contract; retain concrete examples with known answers. |
| Bounded operation sequences / co-simulation | State transitions interact across components or resets | Track independent invariants after each step; record seed and step on failure. |
| Fuzzing / malformed wire tests | Parsers or protocol boundaries accept untrusted bytes | Bound input size, time, memory, and effects; preserve a small reproducer for each defect. |
| Golden binary/text vectors | Cross-language or persisted format compatibility is a contract | Inspect semantic changes before updating expected vectors; exclude only permitted variable fields. |
| Emulator / artifact / hardware-in-the-loop tests | Linking, configuration, MMIO, or component interaction changes | Exercise the delivered artifact or real cooperating components with their declared dependencies. |

An encode/decode round trip alone may preserve the same bug in both directions. Add known valid and invalid binary vectors.
