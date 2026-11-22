# JavaScript and TypeScript

Use this guide with the [code-quality index](README.md) and [readability principles](readability.md). Apply it to browser code, Node tooling, and tests.

## Writing readable code

- Name values by meaning and units: `refreshMs`, `observedAt`, `responseBytes`. Keep transport values distinct from validated models and display strings.
- Use `const` for bindings that are not reassigned and `let` for changing state. Prefer explicit branches over nested ternaries or chained side effects.
- Keep parsing, sorting/filtering, network access, and DOM updates independently understandable. A small pure helper is useful when it names a real rule.
- Pass clocks, timers, and transport into stateful polling code so tests control time and failure. Keep one owner for request cancellation and teardown.
- Do not add global mutable state, a framework, or an abstraction layer to shorten one file.
- Document why a stale value is retained, why a response is refused, or why two observations cannot be combined.

## Validate data at the boundary

JSON parsing establishes syntax, not a usable application model. Validate object shape, schema version, finite numeric values, enum membership, string/list bounds, timestamp meaning, and cross-field relationships before rendering or deciding.

```javascript
function parseQueueDepth(value) {
  if (!Number.isSafeInteger(value) || value < 0) {
    throw new TypeError("queue depth must be a non-negative safe integer");
  }
  return value;
}
```

- Treat missing, malformed, empty, stale, and healthy evidence as distinct states. Empty collections and failed requests must not become a green summary.
- Render untrusted text with `textContent` or text nodes; do not interpolate it into `innerHTML`.
- Keep management credentials and authorization decisions server-side.

## Async work and interface states

- Check HTTP status and content type explicitly; a fulfilled `fetch()` can carry an HTTP error.
- Bound body size and request time. Abort superseded or timed-out requests, release timers, and prevent an older response from overwriting a newer result.
- Handle each promise at its owner. Distinguish cancellation from service failure; avoid overlapping polls and retries without a finite policy.
- Use native buttons, links, labels, and disclosure elements. Preserve keyboard focus across updates and describe states in text, not color alone.

## TypeScript

- Enable `strict` checking in `tsconfig.json`. Model lifecycle alternatives with discriminated unions and check nullable values.
- Treat external values as `unknown` until runtime checks establish their shape. `as SomeType`, non-null assertions (`!`), and generated interfaces do not validate a response at runtime.
- Avoid `any`, blanket suppressions, and elaborate generic types when a concrete model is clearer.
