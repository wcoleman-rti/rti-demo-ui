# Native Release Manual Tests

Use this guide for each release candidate before publication. It supplements,
but does not replace, hosted CI and the release artifact checks. Run the tests
on an interactive desktop with a hardware GPU, not an Xvfb or other headless
session. Record the results using the [template](#review-record-template).
Do not treat an untested or blocked check as a pass.

The currently release-supported configurations are the Python and C++ Linux
native hosts on Ubuntu 22.04+ x86-64, using GTK 3 and WebKitGTK 4.1. Run the
checks for **both hosts**, in a native Wayland session and with the X11 backend
(an X11 session or XWayland). Record each host/backend combination separately.
Windows and macOS have automated qualification but remain pending manual
acceptance; this Linux procedure does not qualify them for release support.
See the [support matrix and platform prerequisites](native-webview.md#support-and-qualification).

## 1. Prepare the candidate

Check out the exact candidate commit in a clean source tree. Run these commands
from its root and record both values. If the eventual release commit differs,
verify that its tree matches the tested tree or repeat the tests.

```bash
git status --short
git rev-parse HEAD
git rev-parse 'HEAD^{tree}'
```

Obtain the `verified-release` artifact from the successful, non-publishing
Release workflow for that same commit. In the example below, replace
`RUN_ID` with that workflow run's numeric ID; check that the displayed SHA
matches the candidate before continuing. Use a new empty directory so files
from another run cannot be mistaken for this candidate.

```bash
RUN_ID=REPLACE_WITH_RUN_ID
gh run view "$RUN_ID" --json headSha,event,conclusion,url
mkdir manual-release-artifacts &&
  gh run download "$RUN_ID" --name verified-release \
    --dir manual-release-artifacts &&
  (cd manual-release-artifacts && sha256sum --check SHA256SUMS)
```

Require `event` to be `workflow_dispatch`, `conclusion` to be `success`, and
every checksum to pass. If the output directory already contains files, use a
different empty directory. Review the artifact names and versions as well.

Install the Linux prerequisites from the [platform instructions](native-webview.md#linux),
including Python, CMake, GTK 3 and WebKitGTK 4.1. Install the Orca screen reader
and `glxinfo` for the checks below. The SVG icon requires a GdkPixbuf SVG
loader. The `gh` CLI must be authenticated to download the workflow artifact.

```bash
sudo apt-get install orca mesa-utils librsvg2-common
```

On Ubuntu with Python 3.11 installed (or substitute `python3.12`):

```bash
python3.11 -m venv .venv-manual-release
```

On Ubuntu with Python 3.13 or newer, use the matching distro Python and its
`python3-gi` package:

```bash
python3 -m venv --system-site-packages .venv-manual-release
```

Then install the candidate wheels and build the C++ test host. The Python
host uses the downloaded wheels; the source-only C++ native companion and
its core are built from the candidate checkout. The C++ release bundle is
independently exercised by the release workflow's installed-consumer tests.

```bash
.venv-manual-release/bin/python -m pip install \
  manual-release-artifacts/rti_demo_ui-*.whl \
  manual-release-artifacts/rti_demo_ui_native-*.whl
cmake -S native/cpp -B build-manual \
  -DBUILD_TESTING=ON -DRTI_DEMO_NATIVE_REAL_ENGINE_TESTS=ON
cmake --build build-manual --target rti_demo_ui_native_manual_release --parallel
```

Confirm the wheel filenames contain the candidate version. These commands create
only a local test environment and build; they do not publish anything.

## 2. Launch commands

Run the following separately for Python and C++ from a terminal in the candidate
root. First run in a Wayland session with `BACKEND=wayland`, then repeat using
`BACKEND=x11` in X11 or XWayland. Confirm the actual session/backend in the
record. When using a desktop launcher later, it must receive the same backend
setting.

```bash
# Choose one: wayland or x11
BACKEND=wayland
ICON="$PWD/tests/fixtures/native_webview_manual/icon.svg"

# Python host
GDK_BACKEND="$BACKEND" .venv-manual-release/bin/python \
  native/python/tests/manual_release.py --icon "$ICON" \
  --application-id org.rti.manualpython

# C++ host, in a separate run
GDK_BACKEND="$BACKEND" \
  ./build-manual/tests/rti_demo_ui_native_manual_release --icon "$ICON" \
  --application-id org.rti.manualcpp
```

Each command should print a loopback URL and open a **Native release manual
test** window. The fixture intentionally requests a nonexistent 3D model;
the fallback message is expected. If a host fails to start or reports an icon
error, record a failure and retain its terminal output.

## 3. Perform the checks

Perform **every** check below for each host/backend combination. Unless a
check says to relaunch, use the window and terminal from the launch commands.
The fixture's local page, rendering probes and Scene3D fallback are the same
for both hosts.

Linux CI drives the actual X11 native windows with keyboard and mouse input
and checks commands, live Scene3D selection, accessibility roles and selected
state, local navigation, resizing at GTK scales 1 and 2, desktop launcher and
icon identity, close, signal and port cleanup. Separate native conformance
tests check Canvas and WebGL pixel readback. CI uses Xvfb and software
rendering; it does not qualify a real Wayland session, hardware GPU, desktop
shell, monitor transitions, or screen-reader experience.

### M1. Window integration

Launch the host. Verify the native title bar looks appropriate for the desktop
and the page shows **Native release manual test**.

### M2. Scaling and multiple monitors

At normal desktop scaling, confirm text and controls are legible and usable.
Change the desktop to a high-DPI scale, resize the window, and type in **Name**.
Move the window between monitors with different scaling if available; check
that it stays legible, correctly sized and interactive. Record actual scale
factors. If the required display configuration is unavailable, mark the
affected check **blocked**, not passed.

### M3. Canvas and hardware WebGL

The Canvas 2D probe must show a yellow rectangle on a blue background; the
WebGL probe must be red and show a `WebGL renderer:` status, not `WebGL
unavailable`. Record that status and hardware-GPU evidence from the system,
for example:

```bash
glxinfo -B
```

Record the renderer/device and how hardware acceleration was confirmed.
`glxinfo` describes the X11/XWayland context, so it alone does not establish
which device a Wayland WebKit context used. A masked/ambiguous renderer or a
software renderer is not evidence of a hardware-GPU pass; investigate or mark
the hardware check blocked.

### M4. Screen-reader usability

Start Orca from another terminal:

```bash
orca --replace
```

In the fixture window, use Tab to reach **Name** and **Greet**. Verify Orca
announces their names and roles as you move between them. Continue tabbing
past the camera controls to a **Scene nodes** option. Use the arrow keys to
move to `tool`, then press Space. Verify the option and its selected state are
announced. A visible accessibility tree alone is not enough for this check.
Record the screen reader and its behavior; if audio or the screen reader is
unavailable, mark the check blocked.

### M5. Linux desktop entry and icon

Run this once per backend in the candidate root in the active desktop session.
It creates two uniquely named per-user test launchers, one for each host, and
refuses to overwrite an existing launcher. Use a checkout path without quotes,
backslashes, percent signs or newlines; desktop-entry `Exec` has its own
escaping rules. Set `BACKEND` to `wayland` or `x11` for the session being tested.

```bash
BACKEND=wayland  # use x11 for the X11/XWayland run
ROOT="$PWD"
ICON="$ROOT/tests/fixtures/native_webview_manual/icon.svg"
DESKTOP="$HOME/.local/share/applications"
CPP_ENTRY="$DESKTOP/org.rti.manualcpp.desktop"
PY_ENTRY="$DESKTOP/org.rti.manualpython.desktop"
mkdir -p "$DESKTOP"
if [ -e "$CPP_ENTRY" ] || [ -L "$CPP_ENTRY" ] ||
   [ -e "$PY_ENTRY" ] || [ -L "$PY_ENTRY" ]; then
  echo "Test launcher already exists; choose a clean test account." >&2
else
  (
  set -C
  {
    printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=RTI Manual C++'
    printf 'Exec=/usr/bin/env GDK_BACKEND=%s "%s" ' \
      "$BACKEND" "$ROOT/build-manual/tests/rti_demo_ui_native_manual_release"
    printf -- '--icon "%s" --application-id %s\n' \
      "$ICON" org.rti.manualcpp
    printf 'Icon=%s\nStartupWMClass=%s\nTerminal=false\n' \
      "$ICON" org.rti.manualcpp
  } > "$CPP_ENTRY" &&
  {
    printf '%s\n' '[Desktop Entry]' 'Type=Application' 'Name=RTI Manual Python'
    printf 'Exec=/usr/bin/env GDK_BACKEND=%s "%s" ' \
      "$BACKEND" "$ROOT/.venv-manual-release/bin/python"
    printf '"%s" --icon "%s" ' "$ROOT/native/python/tests/manual_release.py" "$ICON"
    printf '%s\n' '--application-id org.rti.manualpython'
    printf 'Icon=%s\nStartupWMClass=%s\nTerminal=false\n' \
      "$ICON" org.rti.manualpython
  } > "$PY_ENTRY"
  )
fi
```

If either launcher already existed or creation failed, stop and do not launch
or remove an existing launcher. If creation failed partway through, remove
only a launcher that this attempt created.
Otherwise, close any existing fixture window. Launch each corresponding entry
from the application menu or with:

```bash
gtk-launch org.rti.manualcpp
gtk-launch org.rti.manualpython
```

For each, verify the test icon (a yellow circle with a dark cross on blue) in
the menu, window overview and Alt-Tab, and verify that the window belongs to
the correct launcher. Record each host's result separately. After testing both,
close the windows and remove only the two test launchers created above. Recreate
them with the other backend for the second run.

```bash
rm "$CPP_ENTRY" "$PY_ENTRY"
```

## Review record template

Copy this block into the release PR or its linked release-acceptance record.
Use **PASS**, **FAIL**, or **BLOCKED** for each item, with evidence or a
blocker. Make one copy per host/backend combination; do not combine results.
Link logs or screenshots where useful, without including credentials or other
sensitive data.

```markdown
### Native manual release record

- Candidate version:
- Candidate commit and tree:
- Passing CI run URL:
- Release dry-run URL and artifact checksum result:
- Reviewer and date:
- Host: Python / C++
- OS/version/architecture:
- Backend: Wayland / X11 / XWayland
- Desktop environment/version:
- WebKitGTK and GTK versions:
- Screen reader/version:
- GPU, renderer and hardware-acceleration evidence:
- Monitor(s) and scale factors:

| Check | PASS / FAIL / BLOCKED | Evidence or blocker |
| --- | --- | --- |
| M1 Window integration | | |
| M2 Scaling and multiple monitors | | |
| M3 Canvas and hardware WebGL | | |
| M4 Screen-reader usability | | |
| M5 Desktop entry and shell icon | | |

- Issues or follow-up links:
- Overall result: PASS / FAIL / BLOCKED
```

The release owner should verify that every required host/backend record passes,
that the records and dry-run artifacts match the candidate, and that failures
or blockers have been resolved before publishing.
