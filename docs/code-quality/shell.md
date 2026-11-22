# Shell Authoring and Review Guide

Read the [code-quality index](README.md) and [shared readability rules](readability.md) first. Shell is useful for short, explicit orchestration. Put substantial parsing, policy, or lifecycle state in a tested module suited to that responsibility.

## Choose and honor the interpreter

- Declare the interpreter in the shebang. Use POSIX syntax for `sh`; Bash arrays, `[[ ... ]]`, process substitution, and `pipefail` are not portable `sh` features.
- Match the service, package-maintainer hook, or caller that executes the script. A shebang does not help if a caller explicitly runs `sh script`.
- Keep argument parsing near the entrypoint and work in named functions. Make required tools, inputs, outputs, privilege, and exit codes easy to find.
- Prefer small helpers with explicit arguments over shared mutable globals. Give environment overrides a documented default, validation, and purpose.
- Resolve repository or packaged resources from their defined location. Do not depend on the caller's working directory or a workstation home path.

## Pass data as arguments

- Quote expansions that represent one argument. Use Bash arrays when constructing commands; do not concatenate a command string and execute it with `eval`.
- Use `--` to end options when the invoked program supports it. Validate input according to the command's contract, including values beginning with `-`.
- Use `printf` with a literal format for arbitrary text. Do not parse `ls`, and do not rely on whitespace splitting for filenames or structured records.
- Handle filenames with spaces and glob characters. Use NUL-delimited iteration when arbitrary filenames must be processed and the selected tools support it.
- Keep secrets out of arguments, tracing, and error messages. Avoid `set -x` around credential handling; do not assume redaction elsewhere makes it safe.

```bash
#!/usr/bin/env bash
set -u

check_script() {
    local script_path="$1"
    local result=0
    local -a command=(bash -n -- "$script_path")

    "${command[@]}" || result=$?
    if (( result != 0 )); then
        printf 'Syntax check failed: %s\n' "$script_path" >&2
        return "$result"
    fi
}

if (( $# != 1 )); then
    printf 'Usage: %s SCRIPT\n' "$0" >&2
    exit 2
fi
check_script "$1"
```

## Make failure and cleanup explicit

- `set -euo pipefail` can support a Bash script's policy, but it is not a complete failure model. `errexit` has context-dependent exceptions, and command substitutions and pipelines need deliberate handling.
- Check critical state changes explicitly. Avoid `local output=$(command)` when the declaration masks the command's status; separate declaration and execution.
- Distinguish expected negative results from errors. For example, a search that finds no match is different from an unreadable input or invalid invocation.
- Do not append `|| true` to cleanup, validation, or rollback merely to keep the script moving. Handle a deliberately tolerated outcome by name and reason.
- Preserve the primary failure while reporting cleanup failures. Never describe teardown or rollback as successful when a required step failed or is unknown.
- Own background processes explicitly. Track their identities, wait for them, and define signal/timeout cleanup. Starting a background job is not completion.
- Use traps deliberately: preserve exit status, avoid double cleanup, and make cleanup safe if initialization completed only partly.

## Files, permissions, and environment

- Create temporary files/directories through `mktemp` in a caller-owned location. Clean up only resources created by this invocation.
- Set intended permissions and ownership before publishing a file to a different role account. Atomic rename alone does not prove durability or safe ownership.
- Check required tools before a destructive transition. Keep locale and environment assumptions explicit when they affect parsing or output.
- Use bounded retries and deadlines for external commands. Retry only when the operation's idempotency and uncertain-outcome handling permit it.

## Validation and review checklist

Run `shellcheck` (honoring `.shellcheckrc`) and syntax checks (`bash -n` / `sh -n`) across all modified scripts, including extensionless entrypoints.

- Does the declared interpreter match every feature and actual invocation?
- Are command arguments, working directories, and environment inputs explicit?
- Can a failed pipeline, substitution, or cleanup be mistaken for success?
- Are temporary resources, background processes, and signals owned and bounded?
- Does validation cover extensionless hooks and behavioral failures when relevant?

## References

- [Bash Reference Manual](https://www.gnu.org/software/bash/manual/bash.html)
- [ShellCheck documentation](https://www.shellcheck.net/wiki/)
