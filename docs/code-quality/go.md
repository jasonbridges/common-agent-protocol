# Go Authoring and Review Guide

Read the [code-quality index](README.md) and [shared readability guide](readability.md) with this page. Apply the consuming repository's `AGENTS.md`, accepted ADRs, and committed build configuration (`go.mod`, `MODULE.bazel`, `BUILD.bazel`) first.

## Names, packages, and APIs

- Use `gofmt` for Go source. Follow established Go naming and initialisms; let local names be short when their role is obvious, and make boundary names precise.
- Organize packages around cohesive behavior. Keep `cmd/` focused on configuration, wiring, lifecycle, and exit status; place reusable logic behind narrow APIs.
- Export only what another package needs. Document exported contracts, including ownership, units, empty values, and concurrency behavior where they matter.
- Prefer concrete types. Introduce a small interface at its consumer when it expresses a real dependency; do not duplicate every implementation as an interface.
- Use a struct for related named values. Avoid generic maps, boolean switches, reflection, and type assertions where an ordinary typed API is clearer.
- Keep dependencies explicit. Avoid environment discovery or background work in `init`; construct clients and workers at the application's composition boundary.
- Preserve `nil` versus empty collection semantics where JSON/protobuf consumers can observe the difference. Choose pointer or value receivers consistently with mutation and ownership; never copy a value containing an active mutex.

## Errors and validation

Validate external configuration and protocol messages before domain operations. An `error` is an outcome to handle or return. Add useful context when crossing a layer; use `%w` when callers should be able to inspect the cause with `errors.Is` or `errors.As`. Avoid classifying failures by matching their text.

```go
package capacity

import (
	"context"
	"fmt"
)

// Snapshot contains the available execution slots for one node.
type Snapshot struct {
	Slots int
}

// Reader supplies a snapshot using the caller's deadline and cancellation.
type Reader interface {
	ReadCapacity(ctx context.Context, nodeID string) (Snapshot, error)
}

// Load reads and validates the capacity reported for a named node.
func Load(ctx context.Context, reader Reader, nodeID string) (Snapshot, error) {
	if nodeID == "" {
		return Snapshot{}, fmt.Errorf("node ID is required")
	}
	snapshot, err := reader.ReadCapacity(ctx, nodeID)
	if err != nil {
		return Snapshot{}, fmt.Errorf("read capacity: %w", err)
	}
	if snapshot.Slots < 0 {
		return Snapshot{}, fmt.Errorf("capacity slots must not be negative")
	}
	return snapshot, nil
}
```

Do not discard a failure with `_` simply to satisfy the compiler. If an error is irrelevant by contract, explain why at the call site. Keep routine failures out of `panic`/`recover`. Library code should return control to its caller; process exit and final logging belong to the entrypoint. Do not log the same propagated failure at every layer or include secrets in wrapped errors.

## Resources and concurrency

- Register cleanup after acquisition succeeds. A `defer` runs when the enclosing function returns, so use a helper or explicit cleanup in a long-running loop.
- Check writes and required flush/close operations. Preserve the original failure if cleanup also fails; do not report clean publication or teardown prematurely.
- Pass `context.Context` explicitly to operations that need deadlines/cancellation. Do not replace a request context with `context.Background()` to hide cancellation or use context values as a general configuration bag.
- Give every goroutine a bounded workload, cancellation path, and owner that waits for completion. State which goroutine closes each channel and who owns shared data.
- Keep lock scope clear. Avoid I/O or callbacks while holding a lock unless the design requires it and its blocking behavior has been reviewed.
- Prefer synchronous APIs when callers can decide whether to run them concurrently. Test cancellation, early return, and shutdown; a successful happy path does not establish that workers cannot leak or continue mutating state after return.

## Build, test, and reviewer checks

Run the repository's authoritative test and vet commands (e.g., `bazel test ...` or `go test -race ...`), reporting clearly if a plain `go test` run omits Bazel-built artifacts or race instrumentation.

Check that package boundaries reflect responsibilities, APIs expose ownership, errors retain actionable meaning, and concurrent work finishes or cancels cleanly. Review table-driven cases for distinct behaviors, malformed inputs, and failure paths; avoid test tables that obscure setup or assertions.

## Upstream references

- [Go Code Review Comments](https://go.dev/wiki/CodeReviewComments)
- [Effective Go](https://go.dev/doc/effective_go)
- [`context`](https://pkg.go.dev/context), [`errors`](https://pkg.go.dev/errors), [`sync`](https://pkg.go.dev/sync), and [`testing`](https://pkg.go.dev/testing)
