# Git Operations

- Never bypass Git hooks, including with `--no-verify` or altered hook paths.
- If a commit hook needs network access, retry the normal `git commit` with
  `requestUnsandboxedExecution: true`; do not bypass the hook.
- Request unsandboxed execution for `git push`.
