#!/usr/bin/env bash
set -euo pipefail

system_info() {
  . /etc/os-release
  printf 'OS: %s (%s)\nDesktop: %s\nSession: %s\n' \
    "$PRETTY_NAME" "$(uname -m)" "${XDG_CURRENT_DESKTOP:-unknown}" \
    "${XDG_SESSION_TYPE:-unknown}"
  printf 'GTK: '
  pkg-config --modversion gtk+-3.0
  dpkg-query -W -f='WebKitGTK: ${Version}\n' libwebkit2gtk-4.1-0
  orca --version
}

monitors() {
  /usr/bin/python3 - <<'PY'
from gi.repository import Gio

bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
reply = bus.call_sync(
    "org.gnome.Mutter.DisplayConfig",
    "/org/gnome/Mutter/DisplayConfig",
    "org.gnome.Mutter.DisplayConfig",
    "GetCurrentState",
    None, None, Gio.DBusCallFlags.NONE, -1, None,
)
_, _, logical_monitors, _ = reply.unpack()
for connector, scale in sorted(
    (output[0], scale)
    for _, _, scale, _, _, outputs, _ in logical_monitors
    for output in outputs
):
    print(f"{connector}: {scale * 100:g}%")
PY
}

launcher() (
  host=$1 backend=$2 work=$3
  root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../.." && pwd -P)
  work=$(cd -- "$work" && pwd -P)
  case "$root$work" in
    *[!a-zA-Z0-9_./\ -]*)
      echo 'Checkout and scratch paths may contain only letters, digits, spaces, _, ., /, and -.' >&2
      return 1 ;;
  esac

  case "$backend:${XDG_SESSION_TYPE:-}" in
    wayland:wayland|x11:x11|x11:wayland) ;;
    *) echo "Cannot test $backend in session ${XDG_SESSION_TYPE:-unknown}." >&2; return 1 ;;
  esac
  case "$host" in
    python)
      id=org.rti.manualpython
      name='RTI Manual Python'
      [[ -x "$work/venv/bin/python" ]] || { echo 'Build the Python test environment first.' >&2; return 1; }
      exec_line="\"$work/venv/bin/python\" \"$root/native/python/tests/manual_release.py\"" ;;
    cpp)
      id=org.rti.manualcpp
      name='RTI Manual C++'
      [[ -x "$work/build/tests/rti_demo_ui_native_manual_release" ]] ||
        { echo 'Build the C++ test host first.' >&2; return 1; }
      exec_line="\"$work/build/tests/rti_demo_ui_native_manual_release\"" ;;
    *) echo "Unknown host: $host" >&2; return 1 ;;
  esac

  icon="$root/tests/fixtures/native_webview_manual/icon.svg"
  entry="${XDG_DATA_HOME:-$HOME/.local/share}/applications/$id.desktop"
  mkdir -p -- "$(dirname -- "$entry")"
  temp=$(mktemp -- "${entry}.XXXXXX")
  trap 'rm -f -- "$temp"' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  printf '%s\n' '[Desktop Entry]' 'Type=Application' "Name=$name" \
    "Exec=/usr/bin/env GDK_BACKEND=$backend $exec_line --icon \"$icon\" --application-id $id" \
    "Icon=$icon" "StartupWMClass=$id" 'Terminal=false' > "$temp"
  ln -T -- "$temp" "$entry"
  trap 'rm -f -- "$entry" "$temp"' EXIT
  printf 'Open "%s" from the desktop app menu. Close it and press Enter when done.\n' "$name"
  read -r
)

case "${1:-}:$#" in
  system:1) system_info ;;
  monitors:1) monitors ;;
  launcher:4) launcher "$2" "$3" "$4" ;;
  *) echo "Usage: $0 system | monitors | launcher {python|cpp} {wayland|x11} SCRATCH_DIR" >&2; exit 2 ;;
esac
