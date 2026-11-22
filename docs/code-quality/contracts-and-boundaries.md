# Contracts and Boundary Validation

Use this with the [code-quality index](README.md), [readability guide](readability.md), and the component's accepted design and schemas. It provides a way to translate those requirements into code and tests. Component contracts control permitted inputs, compatibility, authorization, and side effects; the examples below do not introduce a new service interface or repository-wide parser policy.

## State the observable contract

Before changing a public function, CLI, configuration reader, or protocol handler, identify its consumers and the behavior they can observe. A small change can use the existing issue or API comment; a new authority or state boundary needs the design required by [`CORE-AGENTS.md §1`](../../CORE-AGENTS.md#1-document-authority-and-conflict-resolution).

| Question | Record enough to implement and test |
| --- | --- |
| Where does the input come from? | Bytes, decoded values, environment, filesystem, verified peer, or stored state; who can influence each |
| What makes a value valid? | Presence, type, units, bounds, encoding, ordering, freshness, and relationships between fields |
| Who may perform the operation? | Trusted identity source, exact resource/action, and the authority that decides |
| What can change? | Permitted reads, writes, subprocesses, network calls, hardware state, and the first irreversible step |
| What does success prove? | Returned value or receipt, durable state when required, and what remains unverified |
| What can fail? | Stable outcome classes, partial effects, cancellation, and caller recovery behavior |
| What must stay compatible? | Existing consumers, supported versions, flags, output, defaults, and persisted formats |

Turn important invariants into case tables. For example, "an invalid target starts no subprocess" describes both an input result and an absence of side effects. "The request failed" alone does not establish the second property.

## Keep the boundary stages explicit

1. **Bound acquisition and decoding.** Apply the component's byte, nesting, collection, and time limits where the resource is consumed. A size check after reading an unbounded response is too late. Authenticate at the appropriate transport or ingress boundary before treating caller identity as trusted.
2. **Validate representation and meaning.** Successful decoding establishes only the decoder's rules. Validate required fields, exact types, allowed ranges, units, and cross-field constraints before constructing trusted domain values.
3. **Resolve and authorize.** Resolve identifiers through the accepted authority. A caller-provided account, tenant, hostname, or path is not proof of permission. Do not turn a convenient existence check into an unauthorized information leak.
4. **Execute through the appropriate adapter.** Keep pure decisions separate from I/O. If state or authorization can change, enforce the required condition at the effect's actual boundary; an earlier read is not an atomic guarantee.
5. **Validate and translate the result.** External responses, hardware registers, and stored records are inputs too. Preserve meaningful failure classes, causes, cancellation, freshness, and uncertainty. Return only the evidence the operation obtained.

These are responsibilities, not a universal ordering algorithm: some interfaces must authorize before parsing sensitive resources, and a transaction may need to combine validation and mutation under its own concurrency control.

### Preserve distinctions the protocol needs

- Distinguish omitted, `null`, empty, zero, malformed, stale, and unauthorized values when the contract assigns them different meanings. Apply defaults only where the contract permits them.
- Do not rely on coercion to establish an exact type. Python booleans can satisfy integer checks; JavaScript conversions and permissive decoders can collapse different representations into the same value.
- Validate original bytes when spelling, duplicate keys, signatures, or digests matter. Once decoding discards a distinction, later validation cannot recover it.
- Normalize only as specified. Trimming a token, resolving a path, lowercasing an identifier, or reserializing signed data can change its security meaning.
- Decide unknown-field behavior from the protocol.

## Worked example: a bounded capacity read

This illustrative JSON endpoint reads one configured node's capacity. Its chosen limits and result names are examples, not a specific service contract.

The request is one object with exactly `node_id` and `max_age_seconds`, with no duplicate keys or `null`. It is at most 1 KiB. `node_id` is a nonempty string; `max_age_seconds` is an integer token from 1 through 300, without boolean, float, or string coercion. An authenticated caller may read only its permitted node IDs. The endpoint comes from trusted configuration, never from a request URL.

The adapter uses the earlier of the caller deadline and its configured request budget, bounds response bytes, and preserves cancellation. Its result contains an integer slot count within that node's configured capacity and a UTC observation time. A sample is fresh only when its age is between zero and the requested maximum, inclusive. An injected UTC clock supplies that comparison; a monotonic clock measures the request budget. Neither timestamp is accepted as identity.

```text
read_capacity(raw, authenticated_principal, context, dependencies):
    request = decode_and_validate_request(raw, limit = 1 KiB)
    target = dependencies.targets.resolve_authorized(
        authenticated_principal, request.node_id, action = read_capacity)
    deadline = earlier(context.deadline, dependencies.request_budget_deadline())
    sample = dependencies.transport.read_bounded(
        target.endpoint, deadline, context.cancellation)
    capacity = validate_sample(sample, target.capacity_limit)
    age = dependencies.utc_clock.now() - capacity.observed_at
    if age < 0:
        return INVALID_SAMPLE
    if age > request.max_age_seconds:
        return STALE_SAMPLE
    return OBSERVED_CAPACITY(capacity.slots, capacity.observed_at)
```

Here `resolve_authorized` returns the same refusal for an absent or disallowed target and never probes it. The trusted target and permitted action are explicit inputs to the adapter. Transport failure returns `UNAVAILABLE`; malformed response data returns `INVALID_SAMPLE`. Neither becomes zero capacity or a success-shaped empty result.

| Case | Expected result | Effect assertion |
| --- | --- | --- |
| Valid permitted node, slots at either configured bound, fresh timestamp | Observed capacity with timestamp | One bounded read of the configured endpoint |
| Oversized body, duplicate key, extra field, missing field, or `null` | Invalid request | No target probe |
| Age is `true`, `1.5`, `30.0`, `"30"`, zero, or above 300 | Invalid request | No target probe |
| Unknown or disallowed node ID | Target not allowed | No target probe or target-existence disclosure |
| Negative/excessive/non-integer slots or malformed timestamp | Invalid sample | No invented capacity result |
| Sample exactly at age limit; sample beyond limit; future sample | Observed capacity; stale sample; invalid sample, respectively | Result preserves the declared boundary |
| Backend timeout or invalid response bytes | Unavailable or invalid sample, respectively | No default success and no automatic retry |
| Caller cancels during the read | Cancellation propagated after owned cleanup | No detached read continues beyond its cleanup contract |

Test the request validator and sample validator with ordinary values. Exercise the real decoding adapter for lexical cases, including duplicates and numeric forms; a decoder that collapses `30.0` into `30` needs an earlier representation check. Use a strict recording transport for target and deadline assertions, and fixed clock values for both sides of the freshness boundary.

## Apply the same reasoning to other boundaries

For a CLI, document flag precedence, stdin handling, exit codes, and which output is machine-readable. For a state file or flash/disk record, include format/version, endianness, checksum/signature, ownership, mode, and permitted recovery. For subprocesses, keep arguments separate from shell syntax and bound execution/output. A validated path string alone does not establish the identity of a file opened later; follow the component's descriptor, symlink, ownership, and replacement rules.

## Review and validation

- Can a reviewer name every trusted input and the source of its authority?
- Do malformed, unauthorized, stale, and oversized inputs stop at the intended boundary, with tests for both the result and prohibited effects?
- Do errors preserve the information callers need without exposing sensitive data?
- Can a refactor change defaults, coercion, error mapping, or compatibility silently?
- Do tests exercise the real parser/adapter where a pure-value test is insufficient?

## Further reading

- [OWASP Input Validation Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Input_Validation_Cheat_Sheet.html): field-level syntax and semantic checks, parser resource limits, and the separate need for authorization.
- [Python 3.11 JSON compliance and interoperability](https://docs.python.org/3.11/library/json.html#standard-compliance-and-interoperability): default handling of duplicate names, non-finite numbers, and decoder limits.
