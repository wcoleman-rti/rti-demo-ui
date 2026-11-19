# Native release manual tests

## Report template

Paste into the release PR. Copy the session block once per backend. Run both
hosts on Ubuntu 22.04+ x86-64: native Wayland and either X11 or XWayland. No Xvfb.

```markdown
### Native release acceptance

- Candidate version:
- Candidate commit:
- Candidate tree:
- Passing CI URL:
- Release dry-run URL:
- Artifact checksums: PASS / FAIL

#### Session: Wayland / X11 / XWayland

- System output:
- M2 monitor scales (shared if identical for both hosts):
  - 100%:
  - Above 100%:
  - Mixed:

| Check | Python | C++ |
| --- | --- | --- |
| M1 Window | | |
| M2a Live scale change | | |
| M2b Move across scales | | |
| M3 Orca | | |
| M4 Shell launcher and icon | | |

- Exceptions (host, check ID, observed mismatch or blocker):
- Session result: PASS / FAIL / BLOCKED
```

Use **PASS** if all listed expectations hold, **FAIL** if an observation
differs, or **BLOCKED** if a prerequisite prevents the check. Explain only
non-passes. **DEFERRED** is allowed only for M3 below. Session result: **FAIL**
if any check failed, otherwise **BLOCKED** if any is blocked, otherwise **PASS**.
Both session results must pass. If the release commit changes, verify the
release tree still matches the reported tree or rerun the checks.

## Manual tests

### 1. Candidate and setup

From the clean candidate checkout root, with authenticated `gh`, run:

```bash
git status --short
git rev-parse HEAD 'HEAD^{tree}'
read -rp 'Passing CI run ID: ' CI_ID
read -rp 'Release dry-run ID: ' RUN_ID
gh run view "$CI_ID" --json workflowName,headSha,conclusion,url
gh run view "$RUN_ID" --json workflowName,headSha,event,conclusion,url
```

Expect empty status and two successful runs for `HEAD`: **CI** and
**Release** (`workflow_dispatch`). Record commit, tree, and URLs.

```bash
WORK=$(mktemp -d)
REVIEW=tests/fixtures/native_webview_manual/review.sh
gh run download "$RUN_ID" --name verified-release --dir "$WORK/artifacts" &&
  (cd "$WORK/artifacts" && sha256sum --check SHA256SUMS)
```

Expect all checksums `OK` and the Python wheel filenames to contain the
candidate version. Record **Artifact checksums** and **Candidate version**.
Stop if any candidate or artifact check fails.

Install the [Linux prerequisites](native-webview.md#linux), then run:

```bash
sudo apt-get install orca librsvg2-common
python3.11 -m venv "$WORK/venv"  # python3.12 also works
```

On Ubuntu with Python 3.13+, use the distro `python3`, install `python3-gi`,
and replace the venv command with `python3 -m venv --system-site-packages "$WORK/venv"`.

```bash
"$WORK/venv/bin/python" -m pip install \
  "$WORK"/artifacts/rti_demo_ui-*.whl "$WORK"/artifacts/rti_demo_ui_native-*.whl
cmake -S native/cpp -B "$WORK/build" \
  -DBUILD_TESTING=ON -DRTI_DEMO_NATIVE_REAL_ENGINE_TESTS=ON
cmake --build "$WORK/build" --target rti_demo_ui_native_manual_release --parallel
```

Expect all commands to succeed. Run `printf '%s\n' "$WORK"` to get the
scratch path. In a new terminal, set `WORK` to that path and `REVIEW` as above.

### 2. System info

```bash
bash "$REVIEW" system
```

Paste the output into **System output** once per desktop session. With
`BACKEND=x11`, a Wayland session means **XWayland**; an X11 session means **X11**.

### 3. M1 and M4: window and launcher

```bash
BACKEND=wayland  # repeat with x11 in an X11 or Wayland session
bash "$REVIEW" launcher python "$BACKEND" "$WORK"
```

1. Open **RTI Manual Python** from the app menu. For C++, rerun with `cpp`
   and open **RTI Manual C++**.
2. **M1:** Expect one window with a title bar and a page heading reading
   **Native release manual test**.
3. **M4:** Expect the fixture icon (yellow circle and dark cross on blue)
   beside the named launcher in the menu and for its window in the overview
   and Alt+Tab. Keep another app open so Alt+Tab shows a switcher.
4. Record **M1** and **M4**. If the launcher is missing, mark M4 **FAIL** and
   the window checks **BLOCKED**. Otherwise, keep the window open for M2 and M3.
   Then close it and press Enter in the launcher terminal to remove the entry.

### 4. M2: display scaling

In another terminal, with the window open, run after each scale configuration:

```bash
bash tests/fixtures/native_webview_manual/review.sh monitors
```

On non-GNOME desktops, copy connector and scale from Display Settings in
`connector: N%` format, sorted by connector.

1. **M2a:** In Display Settings, set the window's display to 100%, then to
   the lowest offered scale above 100%, without relaunching the fixture.
   At each scale, make the window wider and narrower. Clear **Name**, then
   type `Reviewer`. Expect the label, field, and button to remain visible
   and unclipped, and the field to show `Reviewer`.
2. **M2b:** Set the two displays to those different scales and drag the
   window fully onto each display. Expect the same result on both displays.
3. Paste scale output in **M2 monitor scales** and record **M2a** and **M2b**
   separately. Mark a setup you cannot reproduce **BLOCKED**. Restore the
   original display settings.

### 5. M3: Orca

```bash
orca --replace
```

1. Focus the fixture. Tab to **Name**, then **Greet**. Expect Orca to speak
   each name and identify the controls as a text field and a button.
2. Tab past the camera controls to **Scene nodes**. Arrow to `tool`, then
   press Space. Expect Orca to speak `tool` and indicate that it is selected.
3. Record **M3**. If audio is unavailable, mark **BLOCKED**. On Ubuntu
   22.04 with unpatched WebKitGTK 2.50.4 only, mark **DEFERRED** and cite
   [#36](https://github.com/wcoleman-rti/rti-demo-ui/issues/36). If patched, run M3.

CI covers Canvas/WebGL, command and selection behavior, and X11 window checks
under Xvfb. The manual checks cover the real desktop shell, live display
transitions, and spoken feedback.
