#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.
#

"""Exercise the actual Linux native windows using X11 input and AT-SPI."""

import argparse
import os
import re
import shlex
import signal
import socket
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

import gi
from Xlib import X, display, protocol

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib  # noqa: E402


ROOT = Path(__file__).resolve().parents[3]
TITLE = "Native release manual test"
ICON = ROOT / "tests/fixtures/native_webview_manual/icon.svg"
APP_ID = "org.rti.demo-ui.manual-release"
DESKTOP_ID = "org.rti.demouimanualrelease"
SCALE = int(os.environ.get("GDK_SCALE", "1"))


def wait_for(description, operation, timeout=20):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        try:
            result = operation()
            if result:
                return result
        except GLib.Error as error:
            # The accessibility tree is briefly unavailable during navigation.
            last_error = error
        time.sleep(0.1)
    detail = f": {last_error}" if last_error else ""
    raise AssertionError(f"timed out waiting for {description}{detail}")


def descendants(node):
    yield node
    for index in range(node.get_child_count()):
        child = node.get_child_at_index(index)
        if child is not None:
            yield from descendants(child)


def application(pid):
    desktop = Atspi.get_desktop(0)
    for index in range(desktop.get_child_count()):
        child = desktop.get_child_at_index(index)
        if child is not None and child.get_process_id() == pid:
            return child
    return None


def element(app, role, name):
    return next(
        (
            node
            for node in descendants(app)
            if node.get_role() == role and node.get_name() == name
        ),
        None,
    )


def text_present(app, expected, *, prefix=False):
    for node in descendants(app):
        interface = node.get_text_iface()
        if interface:
            text = Atspi.Text.get_text(interface, 0, -1)
            if text == expected or (prefix and text.startswith(expected)):
                return True
    return False


def xdotool(*args):
    return subprocess.check_output(
        ["xdotool", *(str(arg) for arg in args)], text=True, timeout=10
    ).strip()


def click(node, *, offset=30, hold=0):
    rect = node.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
    assert rect.width > offset and rect.height > 0, (rect.width, rect.height)
    xdotool(
        "mousemove",
        (rect.x + offset) * SCALE,
        (rect.y + rect.height // 2) * SCALE,
        "mousedown",
        1,
    )
    if hold:
        time.sleep(hold)
    xdotool("mouseup", 1)


def close_window(window):
    connection = display.Display()
    try:
        target = connection.create_resource_object("window", int(window))
        event = protocol.event.ClientMessage(
            window=target,
            client_type=connection.intern_atom("WM_PROTOCOLS"),
            data=(
                32,
                [connection.intern_atom("WM_DELETE_WINDOW"), X.CurrentTime, 0, 0, 0],
            ),
        )
        target.send_event(event, event_mask=0)
        connection.sync()
    finally:
        connection.close()


def released(url):
    port = int(url.rsplit(":", 1)[1].rstrip("/"))
    with socket.socket() as connection:
        connection.settimeout(1)
        return connection.connect_ex(("127.0.0.1", port)) != 0


def running(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except FileNotFoundError:
        return False
    return stat.rsplit(") ", 1)[1][0] != "Z"


def desktop_host(command):
    with tempfile.TemporaryDirectory(prefix="rti-desktop-test-") as directory:
        root = Path(directory)
        applications = root / "applications"
        applications.mkdir()
        pid_file = root / "host.pid"
        wrapper = root / "launch-host"
        wrapper.write_text(
            "#!/bin/sh\n"
            f"echo $$ > {shlex.quote(str(pid_file))}\n"
            f"exec {shlex.join([*command, '--icon', str(ICON), '--application-id', DESKTOP_ID])}\n"
        )
        wrapper.chmod(0o700)
        desktop = applications / f"{DESKTOP_ID}.desktop"
        desktop.write_text(
            "[Desktop Entry]\n"
            "Type=Application\n"
            "Name=RTI Native CI\n"
            f"Exec={wrapper}\n"
            f"Icon={ICON}\n"
            f"StartupWMClass={DESKTOP_ID}\n"
            "Terminal=false\n"
        )
        subprocess.run(["desktop-file-validate", str(desktop)], check=True, timeout=10)
        environment = {
            **os.environ,
            "XDG_DATA_HOME": str(root),
            "GDK_BACKEND": "x11",
            "NO_AT_BRIDGE": "0",
        }
        pid = None
        with tempfile.TemporaryFile(mode="w+t") as output:
            try:
                subprocess.run(
                    ["gtk-launch", DESKTOP_ID],
                    env=environment,
                    stdout=output,
                    stderr=subprocess.STDOUT,
                    check=True,
                    timeout=15,
                )
                pid = int(
                    wait_for(
                        "desktop host PID",
                        lambda: pid_file.read_text().strip()
                        if pid_file.exists()
                        else None,
                    )
                )

                def url_from_output():
                    if not running(pid):
                        raise AssertionError("desktop host exited before opening")
                    output.seek(0)
                    match = re.search(r"http://127\.0\.0\.1:\d+/", output.read())
                    return match.group(0) if match else None

                url = wait_for("desktop host URL", url_from_output)
                app = wait_for(
                    "desktop accessible application", lambda: application(pid)
                )
                wait_for(
                    "desktop web page", lambda: element(app, Atspi.Role.HEADING, TITLE)
                )
                window = wait_for(
                    "desktop X11 window",
                    lambda: subprocess.run(
                        [
                            "xdotool",
                            "search",
                            "--pid",
                            str(pid),
                            "--name",
                            f"^{TITLE}$",
                        ],
                        text=True,
                        capture_output=True,
                        check=False,
                    ).stdout.strip(),
                ).splitlines()[-1]
                properties = subprocess.check_output(
                    ["xprop", "-id", window, "WM_CLASS", "_NET_WM_ICON"],
                    text=True,
                    timeout=10,
                )
                assert DESKTOP_ID in properties, properties
                assert "_NET_WM_ICON(CARDINAL)" in properties, properties
                close_window(window)
                wait_for("desktop host exit", lambda: not running(pid))
                assert released(url), f"desktop host still listening at {url}"
            finally:
                if pid is None and pid_file.exists():
                    pid = int(pid_file.read_text().strip())
                if pid is not None and running(pid):
                    os.kill(pid, signal.SIGTERM)
                    wait_for("desktop host cleanup", lambda: not running(pid))
                output.seek(0)
                print(output.read(), end="")


def run_host(command, *, interactive, supplied_icon=None):
    with tempfile.TemporaryFile(mode="w+t") as output:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env={**os.environ, "GDK_BACKEND": "x11", "NO_AT_BRIDGE": "0"},
            stdout=output,
            stderr=subprocess.STDOUT,
        )
        try:

            def url_from_output():
                if process.poll() is not None:
                    raise AssertionError(f"host exited early: {process.returncode}")
                output.seek(0)
                match = re.search(r"http://127\.0\.0\.1:\d+/", output.read())
                return match.group(0) if match else None

            url = wait_for("loopback URL", url_from_output)
            with urllib.request.urlopen(url + "api/state", timeout=5) as response:
                assert response.status == 200
            app = wait_for("accessible application", lambda: application(process.pid))
            wait_for("web page", lambda: element(app, Atspi.Role.HEADING, TITLE))
            window = wait_for(
                "X11 window",
                lambda: subprocess.run(
                    ["xdotool", "search", "--name", f"^{TITLE}$"],
                    text=True,
                    capture_output=True,
                    check=False,
                ).stdout.strip(),
            ).splitlines()[-1]
            xdotool("windowfocus", "--sync", window)
            frame = element(app, Atspi.Role.FRAME, TITLE)
            frame_width = (
                frame.get_component_iface().get_extents(Atspi.CoordType.SCREEN).width
            )
            geometry = xdotool("getwindowgeometry", "--shell", window)
            pixel_width = int(re.search(r"^WIDTH=(\d+)$", geometry, re.MULTILINE)[1])
            assert pixel_width == frame_width * SCALE, (pixel_width, frame_width, SCALE)

            identity = subprocess.check_output(
                ["xprop", "-id", window, "WM_CLASS", "_NET_WM_ICON"],
                text=True,
                timeout=10,
            )
            assert APP_ID in identity, identity
            icon_data = identity.split("_NET_WM_ICON", 1)[1]
            if interactive:
                assert "_NET_WM_ICON(CARDINAL)" in identity, identity

                entry = wait_for(
                    "Name input", lambda: element(app, Atspi.Role.ENTRY, "Name")
                )
                assert element(app, Atspi.Role.PUSH_BUTTON, "Greet")
                assert element(app, Atspi.Role.LINK, "Open local page")
                assert element(app, Atspi.Role.LIST_BOX, "Scene nodes")
                assert entry.get_component_iface().grab_focus()
                xdotool("key", "ctrl+a")
                xdotool("type", "--clearmodifiers", "Reviewer")
                xdotool("key", "Tab", "Return")
                wait_for(
                    "keyboard command result",
                    lambda: text_present(app, "Hello, Reviewer!"),
                )
                assert entry.get_component_iface().grab_focus()
                xdotool("key", "ctrl+a", "BackSpace")
                click(element(app, Atspi.Role.PUSH_BUTTON, "Greet"))
                wait_for(
                    "invalid command error",
                    lambda: text_present(app, "Command failed:", prefix=True),
                )
                assert entry.get_component_iface().grab_focus()
                xdotool("type", "--clearmodifiers", "Mouse")
                click(element(app, Atspi.Role.PUSH_BUTTON, "Greet"))
                wait_for(
                    "mouse command result", lambda: text_present(app, "Hello, Mouse!")
                )

                tool = wait_for(
                    "tool option",
                    lambda: element(
                        app, Atspi.Role.LIST_ITEM, "tool, success, visible"
                    ),
                )
                click(tool, hold=0.35)
                wait_for("tool selection", lambda: text_present(app, "tool: selected"))
                tool = element(app, Atspi.Role.LIST_ITEM, "tool, success, visible")
                assert tool.get_state_set().contains(Atspi.StateType.SELECTED)
                click(tool, hold=0.35)
                wait_for(
                    "tool deselection", lambda: text_present(app, "tool: deselected")
                )
                tool = element(app, Atspi.Role.LIST_ITEM, "tool, success, visible")
                assert not tool.get_state_set().contains(Atspi.StateType.SELECTED)
                rect = tool.get_component_iface().get_extents(Atspi.CoordType.SCREEN)
                click(tool, offset=rect.width - 4, hold=0.35)
                wait_for(
                    "padding selection", lambda: text_present(app, "tool: selected")
                )
                tool = element(app, Atspi.Role.LIST_ITEM, "tool, success, visible")
                assert tool.get_component_iface().grab_focus()
                xdotool("key", "space")
                wait_for(
                    "keyboard deselection",
                    lambda: text_present(app, "tool: deselected"),
                )
                xdotool("key", "Up", "Return")
                wait_for(
                    "keyboard selection", lambda: text_present(app, "base: selected")
                )
                base = element(app, Atspi.Role.LIST_ITEM, "base, success, visible")
                assert base.get_state_set().contains(Atspi.StateType.SELECTED)

                click(element(app, Atspi.Role.LINK, "Open local page"))
                wait_for(
                    "local navigation",
                    lambda: element(app, Atspi.Role.HEADING, "Local navigation test"),
                )
                click(element(app, Atspi.Role.LINK, "Return to manual test"))
                wait_for(
                    "return navigation", lambda: element(app, Atspi.Role.HEADING, TITLE)
                )
                click(element(app, Atspi.Role.PUSH_BUTTON, "Greet"))
                wait_for(
                    "command after navigation",
                    lambda: text_present(app, "Hello, World!"),
                )

                for width in (390, 1200):
                    xdotool("windowsize", "--sync", window, width * SCALE, 800 * SCALE)

                    def controls_fit():
                        for role, name in (
                            (Atspi.Role.ENTRY, "Name"),
                            (Atspi.Role.PUSH_BUTTON, "Greet"),
                        ):
                            control = element(app, role, name)
                            if control is None:
                                return False
                            rect = control.get_component_iface().get_extents(
                                Atspi.CoordType.WINDOW
                            )
                            if rect.width <= 0 or not 0 <= rect.x <= width - rect.width:
                                return False
                        return True

                    wait_for(f"controls to fit resized width {width}", controls_fit)

                close_window(window)
            else:
                assert icon_data != supplied_icon, "default icon matches supplied icon"
                process.send_signal(signal.SIGINT)
            assert process.wait(timeout=15) == 0
            assert released(url), f"server still listening at {url}"
            return icon_data
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            output.seek(0)
            print(output.read(), end="")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", required=True, type=Path)
    parser.add_argument("--cpp", required=True, type=Path)
    args = parser.parse_args()
    Atspi.init()
    hosts = [
        [str(args.python), "-u", str(ROOT / "native/python/tests/manual_release.py")],
        [str(args.cpp)],
    ]
    for command in hosts:
        print(f"Testing {command[0]}", flush=True)
        icon = run_host([*command, "--icon", str(ICON)], interactive=True)
        run_host(command, interactive=False, supplied_icon=icon)
        desktop_host(command)


if __name__ == "__main__":
    main()
