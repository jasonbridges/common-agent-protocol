# Python Authoring and Review Guide

Read the [code-quality index](README.md) and [shared readability guide](readability.md) with this page. It applies to Python source and tests. Follow the consuming repository's `AGENTS.md`, `pyproject.toml`, and `ruff.toml` for the project's syntax floor, formatting, and lint scope.

## Names, types, and module boundaries

- Name values for their domain meaning and unit: `timeout_seconds`, `capacity_bytes`, `lease_id`. Use an `Enum` when a finite state set carries behavior.
- Annotate public functions and important boundaries. Prefer a `dataclass` or a specific mapping type to an unstructured dictionary passed through many layers. Type hints do not validate JSON, environment variables, or API responses at runtime.
- Keep decisions independently testable. Pass configuration, time, and required collaborators explicitly; put network, filesystem, and process work in adapters.
- Keep CLI parsing and exit-code translation in the entrypoint. Place reusable domain behavior in importable functions/modules, preserving the existing CLI contract.
- Split modules by responsibility and dependency direction. Do not create a class, factory, protocol, or one-function module unless it clarifies a real boundary.
- Prefer an ordinary loop when a comprehension would contain several conditions, hide side effects, or require readers to decode nested expressions.

## Imports and initialization

Keep imports grouped at module scope: standard library, third-party dependencies, then first-party modules. Let the repository formatter/linter (e.g., Ruff) order them. Avoid wildcard imports, filename loading, and `sys.path` changes as fixes for an incorrect install or test setup.

Required first-party imports must fail visibly when the package is missing. Do not catch `ImportError` around a whole feature and continue with a partial or different implementation. An optional dependency needs an explicit, tested unsupported state. Importing a module should not contact services, start workers, parse CLI arguments, or change process-wide state.

## Validation and errors

Validate untrusted values once at the boundary and pass a meaningful type inward. Preserve distinctions such as missing, empty, zero, false, malformed, and unknown. Reject unknown fields when the component's schema requires that behavior.

```python
import json
from dataclasses import dataclass


@dataclass(frozen=True)
class Capacity:
    max_workers: int


def parse_capacity(raw: str) -> Capacity:
    try:
        document = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("capacity must be valid JSON") from exc

    if not isinstance(document, dict) or set(document) != {"max_workers"}:
        raise ValueError("capacity requires only max_workers")
    count = document["max_workers"]
    if type(count) is not int or count < 1:
        raise ValueError("max_workers must be a positive integer")
    return Capacity(max_workers=count)
```

The exact `type(count) is not int` check deliberately rejects JSON `true`, which Python otherwise treats as an `int` subtype. An I/O adapter must separately enforce input-size and timeout limits before calling a parser.

Catch only failures the current layer can handle. Preserve an exception's cause with `raise ... from exc` when translating it; keep messages free of secrets. Do not turn an unexpected exception into an empty collection, success, or an automatic retry.

## Resources, mutable state, and concurrency

- Use context managers or `try/finally` for resources. Handle required write, flush, close, and cleanup failures according to the component's durability contract.
- Avoid mutable default arguments and shared mutable module state. Use `default_factory` for per-instance dataclass collections; `frozen=True` does not make a contained list immutable.
- Bound subprocess and network operations. Pass subprocess arguments as a list (`shell=False`); shell execution needs a specific reason and safe handling of every dynamic value.
- Give each thread, task, and child process an owner and a shutdown path. Await or join what you start. Propagate cancellation after cleanup; do not swallow `asyncio.CancelledError` or block the event loop with synchronous I/O.
- Test timing with injected clocks and synchronization points. Use a bounded wait where real concurrency is necessary; arbitrary sleeps are not proof of ordering.

## Validation and reviewer checks

Run the repository's configured Python lint, type-check, and test commands (for example `ruff check`, `mypy`, `python3 -m unittest`, or Bazel test targets).

Before accepting a change, check that names and types expose intent, imports are predictable, expected errors are distinguished from defects, resource cleanup works on failure, and tests demonstrate the changed contract. Read the assertions: mock call counts alone rarely establish an observable outcome.

## Upstream references

- [PEP 8](https://peps.python.org/pep-0008/) for Python naming, imports, and style.
- [Dataclasses](https://docs.python.org/3.11/library/dataclasses.html) for model and default-value semantics.
- [Asyncio tasks](https://docs.python.org/3.11/library/asyncio-task.html) for task ownership and cancellation behavior.
