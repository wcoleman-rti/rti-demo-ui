<!--
  (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.

  RTI grants Licensee a license to use, modify, compile, and create derivative
  works of the Software.  Licensee has the right to distribute object form
  only for use with RTI products.  The Software is provided "as is", with no
  warranty of any type, including any warranty for fitness for any purpose.
  RTI is under no obligation to maintain or support the Software.  RTI shall
  not be liable for any incidental or consequential damages arising out of the
  use or inability to use the software.
-->

# Git Operations

- Never bypass Git hooks, including with `--no-verify` or altered hook paths.
- If a commit hook needs network access, retry the normal `git commit` with
  `requestUnsandboxedExecution: true`; do not bypass the hook.
- Request unsandboxed execution for `git push`.
