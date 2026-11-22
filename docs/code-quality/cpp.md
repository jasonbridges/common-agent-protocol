# C and C++ Authoring and Review Guide

Read the [code-quality index](README.md) and [shared readability rules](readability.md) first. Apply the consuming repository's `AGENTS.md`, accepted ADRs, and committed compiler/toolchain flags when general C/C++ guidance conflicts with a local requirement.

## Architecture and module boundaries

- **Separate `core/` from `platform/` / `app/`:** Keep protocol codecs, state machines, boot policy, and validation in hardware-free C++ (`core/`) that compiles identically for host unit tests, bare-metal, RTOS (e.g., Zephyr), and Linux. Keep register access, OS syscalls, and RTOS primitives in thin platform adapters.
- **Inject boundaries via narrow interfaces:** Pass clocks, storage/block devices, UARTs, mailboxes, and loggers as abstract interfaces (`hal::Clock&`, `storage::BlockDevice&`) so host tests and co-simulations run deterministically without sleeps or hardware.
- **Keep headers minimal:** Prefer forward declarations where sufficient, avoid pulling OS/RTOS headers into `core/`, and keep platform register definitions out of portable headers.

## Memory, ownership, and safety

- **Use non-owning views at boundaries:** Prefer `std::span` / `std::string_view` (or `pw::ByteSpan` / `pw::ConstByteSpan` in Pigweed) with explicit bounds over raw `(ptr, len)` pairs or NUL-terminated assumptions.
- **RAII for OS resources; explicit lifetimes in freestanding code:** On Linux/host, wrap file descriptors, `mmap` windows, locks, and temporary files in RAII types with deleted copy constructors/assignment. In freestanding/RTOS code (`-fno-exceptions -fno-rtti`), prefer static or caller-owned storage and deterministic initialization; avoid dynamic allocation (`new`/`malloc`) unless explicitly part of the target's design.
- **Check all bounds and arithmetic:** Validate offsets, sizes, and lengths against buffer/partition capacities using overflow-safe comparisons (`offset <= total && size <= total - offset`, not `offset + size <= total`) before copying or slicing.
- **Explicit initialization:** Initialize structs and stack arrays (`std::array<std::byte, N> buf{};` or member initializers) so uninitialized padding or stack garbage cannot leak into wire frames, CRCs, or state records.
- **Zeroize sensitive material:** Scrub keys, round keys, and tokens from stack/member buffers on destruction or completion using `volatile` writes or explicit constant-time/secure-erase primitives so the compiler cannot optimize the clear away.

## Wire formats, alignment, and bare-metal rules

- **Explicit endianness — never cast packed structs:** Do not cast raw byte buffers to `struct*` or rely on bitfield layout for on-disk, shared-memory, or wire protocols. Encode and decode multi-byte integers explicitly byte by byte (little-endian or big-endian as specified) and verify magic numbers, versions, sizes, and CRCs/MACs before trusting any field.
- **Alignment and MMU-off / `-mstrict-align` safety:**
  - In bare-metal or MMU-off code (`-mstrict-align`, `-mgeneral-regs-only`), unaligned multi-byte loads/stores fault. Mark DMA/word-accessed stack buffers with `alignas(8)` (or `alignas(4)`) and handle potentially unaligned caller spans via `std::memcpy` into a local aligned word rather than casting `reinterpret_cast<uint64_t*>(ptr)`.
  - Verify bare-metal binaries do not emit FP/SIMD instructions when FP/SIMD state is uninitialized.
- **MMIO and cross-domain shared memory:**
  - Access hardware registers only through explicit `volatile` MMIO helpers (`Read32`/`Write32`, `sys_read32`/`sys_write32`), never plain struct dereferences.
  - Use explicit memory barriers (`dmb sy`, `dsb sy`, `isb`) between shared-memory ring writes and mailbox doorbells across CPU domains, and use word-aligned accesses when device/uncached memory forbids byte-wise or unaligned `memcpy`.
- **Bounded hardware waits:** Every poll of a clock monitor, reset monitor, UART FIFO, or controller busy bit must have a bounded timeout or iteration limit returning a `Status` error rather than hanging forever.

## Errors, state transitions, and concurrency

- **Return explicit status codes:** Use `pw::Status` / `pw::StatusWithSize` (or `std::expected` / `StatusOr`) rather than boolean success flags or errno globals. Do not ignore non-`ok()` statuses silently; when an error is intentionally best-effort (such as a status uplink before reset), document why with `.IgnoreError()` and a comment.
- **Persist before irreversible side effects:** Write durable state (e.g., boot attempt counters, command deduplication markers) before jumping to an untrusted image or acknowledging an external command.
- **Interrupt and thread boundaries:** Keep ISRs minimal (clear interrupt, increment atomic/give semaphore). Guard shared state with explicit locks or single-owner event loops; avoid holding locks across slow UART/SPI/network I/O. Watch 32-bit vs 64-bit tick/uptime counters for signedness and wraparound (`uint32_t` modular subtraction).

## Formatting, static analysis, and testing

- Follow the repository's `.clang-format` and `.clang-tidy` configuration and compile with `-Wall -Wextra` (treat warnings seriously).
- Write unit tests (e.g., GoogleTest) for pure `core/` logic, malformed/truncated/corrupted inputs, boundary values, integer wraparound, and misaligned buffers.
- Use deterministic fakes (in-memory block devices, fake clocks, scripted UART/module peers) and multi-component co-simulation tests rather than timing sleeps.

## Review checklist

- Are hardware/OS calls isolated from `core/` logic, with deterministic host tests covering the logic?
- Are all buffer accesses, integer additions, and offset/length checks overflow-safe?
- Are wire/disk codecs explicit byte-order encoders/decoders with validated magic/version/CRC before use?
- For bare-metal/RTOS: are stack buffers properly aligned, MMIO accesses `volatile`, barriers placed around shared memory, and all hardware poll loops bounded?
- Are 32-bit/64-bit timers and counters wrap-safe without signed overflow or truncation?
