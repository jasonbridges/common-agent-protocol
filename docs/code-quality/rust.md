# Rust Authoring and Review Guide

Read the [code-quality index](README.md) and [shared readability rules](readability.md) first. Apply the consuming repository's `AGENTS.md`, accepted ADRs, and committed toolchain configuration when a general Rust recommendation conflicts with a local requirement.

## Scope and build authority

- Use the repository's authoritative build system and pinned toolchain (for example Bazel `rules_rust` when Bazel is authoritative, or pinned `Cargo.lock` / `rust-toolchain.toml`). Cargo-only checks do not replace Bazel or target-hardware gates when the repository requires Bazel.
- Keep compiler, edition, target triples, linker scripts, crate checksums, features, proc macros, and build-script inputs in the reviewed dependency graph. Do not fetch dependencies from test actions or invoke ambient host `cargo` inside a Bazel shell rule.

## Keep the design easy to follow

- Start with cohesive modules and a small crate set. Add a crate for a real responsibility, `#![no_std]`/target boundary, or trust boundary, or a measured incremental-build benefit — not one crate per source file.
- Separate pure policy, wire codecs, and state transitions (`#![no_std]` core crates where appropriate) from filesystem, Linux, network, MCU HAL, and clock adapters. Keep one explicit owner of lifecycle state.
- Keep exports narrow. Use domain names for functions and types; avoid generic `manager`, `helper`, or `utils` modules that accumulate unrelated behavior.
- Use enums for distinct states and newtypes where IDs, addresses, or units (`Bytes`, `Millis`, `Lba`) are easily confused. Make invalid combinations difficult to construct.
- Prefer ordinary functions and explicit control flow. Introduce traits at useful substitution boundaries (HALs, clocks, storage, transports), not for every struct or free function.
- Keep differently privileged or credentialed work in separate executables and accounts. A Rust module is not a security boundary.

## Make ownership and failure visible

- Borrow data (`&[u8]`, `&str`) when the operation does not need ownership. Return owned data when the caller needs an independent lifetime. Explain material copies; do not add `.clone()` everywhere merely to silence borrow-checker errors.
- Return `Result<T, E>` with typed domain errors for expected configuration, I/O, wire-parsing, transport, and runtime failures. Preserve useful error categories and add context without secrets.
- Handle an error where the recovery policy is known. Do not log-and-continue, convert unknown state into success, or discard a failed durable transition.
- **Zero panics on external or wire inputs:** Avoid `.unwrap()`, `.expect()`, unchecked indexing (`buf[i]`), and panicking arithmetic (`+`, `-`, `*` on untrusted sizes) on externally influenced or firmware runtime paths. Use `.get(...)`, `checked_*` / `saturating_*`, and explicit `Result` propagation. A proven internal invariant needs an explanation; test assertions may panic loudly.
- Validate decoded values before using them. Distinguish absent, invalid, stale, and explicitly configured values where the interface contract distinguishes them.

This illustrative parser keeps conversion and bounds explicit without panicking:

```rust
use core::time::Duration;

#[derive(Debug, PartialEq, Eq)]
pub enum TimeoutError {
    InvalidInteger,
    OutOfRange,
}

pub fn parse_timeout_seconds(raw: &str) -> Result<Duration, TimeoutError> {
    let seconds = raw.parse::<u64>().map_err(|_| TimeoutError::InvalidInteger)?;
    if !(1..=300).contains(&seconds) {
        return Err(TimeoutError::OutOfRange);
    }
    Ok(Duration::from_secs(seconds))
}
```

## Embedded, `#![no_std]`, and bare-metal discipline

When writing `#![no_std]` libraries, bootloaders, or MCU firmware:

- **Fixed widths and endianness:** Never rely on `usize`/`isize` layout or host endianness in on-disk, shared-memory, or wire formats. Use fixed-width integers (`u16`, `u32`, `u64`) and explicit `from_le_bytes` / `to_le_bytes` (or `from_be_bytes`) rather than `#[repr(C)]` struct transmutation.
- **No accidental heap or FP/SIMD:** Keep `#![no_std]` core crates free of `alloc` unless explicitly designed for an allocator. For early-boot/MMU-off targets (such as AArch64 EL2 BL33), use soft-float / `+strict-align` targets and verify generated binaries do not emit FP/SIMD instructions or unaligned device accesses.
- **Bounded memory and stacks:** Prefer fixed-capacity buffers, `heapless` or slice-based APIs, and bounded loops. Avoid deep recursion or large stack-allocated buffers on constrained MCU stacks.
- **Hardware poll loops and watchdogs:** Every hardware register poll (clocks, resets, UART, SDHI, SPI) must have a bounded timeout or iteration limit so a wedged peripheral fails gracefully rather than hanging boot or starving a watchdog.
- **Explicit panic and abort behavior:** Define the panic policy per target (e.g., `panic-halt` / `panic-reset` / fault log) and never silently swallow hardware faults.

## Bound concurrency and `unsafe` operations

- Give each spawned task or thread an owner, cancellation path, and join/cleanup policy. Bound queues, retries, response sizes, and execution time.
- Keep lock scope small. Do not hold a synchronous lock (`std::sync::Mutex` or critical section) across an `.await` or slow blocking I/O. Choose shared ownership (`Arc`) and locking only when the state model needs them.
- Make cancellation and partial completion explicit. Dropping a future is not evidence that an external process stopped or a remote write did not occur.
- **Narrow, audited `unsafe`:** Minimize `unsafe` to unavoidable FFI, MMIO register access, DMA/shared-memory barriers, or assembly entrypoints. Isolate `unsafe` behind safe wrappers with explicit `// SAFETY: ...` comments proving alignment, lifetime, aliasing, and volatility invariants. Use `core::ptr::read_volatile` / `write_volatile` and explicit memory barriers (`dmb sy`, `fence`) where required; never cast arbitrary byte pointers to `&mut T` without proven alignment and initialization.

## Build speed, formatting, and validation

- Use the repository's pinned `rustfmt` and `clippy` configuration. A narrow `#[allow(...)]` needs a concrete reason beside the code; never silence lints globally.
- Keep heavy dependencies and enabled Cargo/crate features justified (`default-features = false` in `#![no_std]` crates). Avoid broad public interfaces that force full downstream rebuilds.
- Test pure decisions, wire round-trips + malformed inputs, boundary values, ownership transfers, cancellation, and recovery. Cross-test shared wire/disk formats against golden binary vectors when interoperating with C/C++/Python.
- Measure clean, warm no-change, and small-edit builds when claiming build-speed improvements. Do not infer a speedup from a single cached run.

## Review checklist

- Can the reviewer identify policy, side effects, lifecycle ownership, and trust boundaries without following a chain of generic wrappers?
- Are all external/wire paths free of `.unwrap()`, `.expect()`, unchecked indexing, and integer overflow?
- Are `unsafe` blocks minimal, isolated, and justified with `// SAFETY:` invariants (alignment, volatile, aliasing, barriers)?
- For `#![no_std]`/bare-metal: are wire formats explicit little/big-endian byte codecs, stacks/buffers bounded, and hardware loops timed out?
- Do tests exercise real failure, malformed-input, boundary, and recovery paths under the repository's authoritative build graph?
