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

"""Interactive native release-checklist host."""

import argparse
from pathlib import Path

from rti_demo_ui import DemoUiApp


def create_app():
    static_root = (
        Path(__file__).resolve().parents[3] / "tests/fixtures/native_webview_manual"
    )
    app = DemoUiApp("Native release manual test", static_root=static_root)
    app.register_command(
        "greet",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1}},
            "required": ["name"],
            "additionalProperties": False,
        },
        lambda payload: {"message": f"Hello, {payload['name']}!"},
    )
    return app


def main():
    from rti_demo_ui_native import run_native

    parser = argparse.ArgumentParser()
    parser.add_argument("--icon", type=Path)
    parser.add_argument("--application-id", default="org.rti.demo-ui.manual-release")
    args = parser.parse_args()
    app = create_app()
    run_native(app, icon=args.icon, application_id=args.application_id)


if __name__ == "__main__":
    main()
