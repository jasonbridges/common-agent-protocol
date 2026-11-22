# Bazel and Starlark Authoring and Review Guide

Read the [code-quality index](README.md) and [shared readability rules](readability.md) first. A clear build graph makes dependencies reviewable and keeps unrelated changes from repeating expensive work.

## Scope and authoritative configuration

Use `.bazelversion`, `MODULE.bazel`, its committed lockfile (`MODULE.bazel.lock`), and `.bazelrc` as the repository's build configuration. Read the affected component's documentation and `AGENTS.md` for supported targets and platforms.

## Write a graph a reviewer can follow

- Give targets names that describe their output or responsibility. Keep source, test, fixture, and generated-output relationships visible in the `BUILD.bazel` file.
- Prefer straightforward declarations over variables or macros introduced solely to remove a few repeated lines. Abstract a stable repeated contract, not every similarity between unrelated targets.
- Keep target and package boundaries cohesive. Split a large target when the dependency or rebuild boundary is useful; avoid a target for every trivial file.
- Declare direct dependencies and narrow visibility. Do not make every library public or add a whole-repository filegroup to avoid finding the real inputs.
- Keep loads, rule declarations, names, and attribute layout consistent with neighboring files and upstream BUILD conventions.
- Document non-obvious Starlark rule contracts: accepted attributes, providers, declared outputs, execution constraints, and failure behavior.

## Declare everything an action uses

- Declare source/configuration inputs, outputs, executable tools, environment, and platform requirements. Resolve tools through reviewed targets/toolchains, not whichever executable happens to appear on the worker's `PATH`.
- Put runtime fixtures in declared `data` / runfiles and resolve them through the supported runfiles mechanism. Tests must not recover missing inputs from the checkout or home directory.
- Separate dependency acquisition from build/test execution. Ordinary actions must not install packages, repin dependencies, or discover mutable host state.
- Use committed locks and pinned commits/hashes for ordinary builds. A new dependency, feature, compiler, generator, or linker input needs the corresponding reviewed resolution change.
- Treat generated files as outputs of declared actions. Keep their source and generator authoritative rather than manually patching generated output.
- Prefer native language rules and explicit actions. Do not hide ambient compilation or tests inside a shell wrapper to make a Bazel label appear green.
- Make required missing tools, fixtures, unsupported platforms, or invalid inputs fail visibly. A test that silently skips its purpose is not qualification.

## Preserve fast incremental builds

- Keep input closures accurate and narrow. Changing a fixture should invalidate its consumers; changing unrelated documentation should not rebuild the world.
- Avoid global timestamps, workflow IDs, hostnames, or whole-tree stamps on pure libraries/tests. Declare values that actually change behavior, and keep release metadata at the output boundary that needs it.
- Reuse compiled outputs during image/package assembly. Do not compile the same source again in a packaging wrapper or launch an independent build inside a test action.
- Keep macros and analysis work bounded. Avoid repeated materialization of large transitive dependency sets; use appropriate providers and `depset`s in rules.
- Measure cold computation, warm no-change, cache restoration, and representative source/interface/test/fixture edits before claiming speedups.

## Validation and review checklist

Distinguish analysis success, compilation, actual test execution, and cached test results. A local hit does not establish cross-runner reuse; a cached source test does not prove live hardware or deployment behavior.

- Do labels and dependencies explain what changes rebuild which outputs?
- Are tools, generated files, runfiles, platforms, and environment declared?
- Do tests execute meaningful assertions and fail for missing prerequisites?
- Does the evidence distinguish cache reuse from fresh execution and live state?
- Are graph expansion, analysis cost, and compilation proportional to the change?

## References

- [Bazel BUILD style](https://bazel.build/build/style-guide)
- [Starlark rules](https://bazel.build/extending/rules)
- [Rules for remote execution](https://bazel.build/remote/rules)
