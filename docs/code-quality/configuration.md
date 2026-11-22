# Configuration, systemd, Containers, and Workflows

Use this guide with the [code-quality index](README.md) and [readability principles](readability.md). Declarative files deserve code review: their ordering, defaults, permissions, and failure behavior affect running systems.

## Start from the consumer and owner

Identify the parser, schema, deployment channel, service account, and accepted architecture before editing. Follow the existing component's format instead of adding a second configuration layer.

## YAML and JSON readability

- Use descriptive keys and stable identifiers. Make units visible and distinguish a value, its file path, a resource identifier, and a secret reference.
- Keep related settings together and preserve meaningful list order when order controls apply or rollback precedence.
- Quote strings that a consumer could interpret as booleans, numbers, or dates. Verify the actual parser/version.
- Explain surprising values and operational reasons in supported comments or description fields.
- Treat missing, empty, zero, and `null` according to the schema. Do not use a truthiness fallback when zero is valid or absence must fail.
- Reject duplicate keys and invalid/unknown values where the component's contract requires it. Preserve bounds and cross-field checks, not only syntax validation.
- Keep secrets out of plaintext configuration, samples, diagnostics, and command arguments.

## systemd units

- Use one canonical unit source and packaged runtime paths. Never commit workstation-local home paths (`/var/home/...`) into units.
- Make account, working directory, executable, state paths, and environment dependencies clear. Check which UID/GID creates and later reads each object.
- Match `Type=`, startup ordering, readiness, restart policy, stop behavior, and timeouts to the actual process. `After=` ordering alone does not start a dependency.
- Keep command lines understandable (`ExecStart=` is not an ordinary shell script).
- Preserve least privilege, resource limits, filesystem restrictions (`NoNewPrivileges=yes`, `ProtectHome=yes`, `PrivateTmp=yes`), and socket boundaries. Never remove hardening to make a test pass.

## Containerfiles

- Separate build inputs from runtime needs. Copy only declared artifacts into the final image and keep its account, entry point, and writable paths explicit.
- Preserve reviewed base-image and toolchain pins. Verify downloaded inputs with SHA-256 checksums or digests; tags alone are mutable.
- Order stable dependency layers before changing source where it helps reuse.
- Do not bake secrets into layers, build arguments, or environment instructions. Preserve rootless and socketless boundaries required by the runner/executor.
- [Docker build best practices](https://docs.docker.com/build/building/best-practices/)

## GitHub Actions

- Give jobs and steps names that explain their result. Keep substantial logic in tested repository scripts and make inputs, outputs, dependencies, and timeout behavior explicit.
- Match each job's capabilities to its workload; a runner label is not proof of authorization.
- Keep default token permissions narrow (`permissions: contents: read`) and widen only the specific trusted job. Never execute untrusted fork PR code in a credentialed `pull_request_target` job.
- Treat PR titles, branch names, issue bodies, and event payloads as untrusted data. Pass them through a structured input or quoted environment variable, not direct `${{ ... }}` interpolation inside shell scripts. See [GitHub's secure-use reference](https://docs.github.com/en/actions/reference/security/secure-use).
- Preserve pinned action revisions and approved dependency acquisition. Do not weaken a failed gate through `continue-on-error`, skipped jobs, or broad filters.

## Validation and review checklist

Run the repository's configured lint/validation commands (e.g., `yamllint`, `actionlint`, `hadolint`, `dtc`, `systemd-analyze`) and affected parser/schema tests, reporting missing tools accurately.

Review effective configuration, defaults, permissions, restart/activation effects, and recovery procedure. Include a refusal case when changing validation. Passing static checks is not a deployment or recovery drill.
