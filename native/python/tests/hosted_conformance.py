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

import argparse
import os
import subprocess
import sys
from pathlib import Path


def run(command, *, environment):
    result = subprocess.run(
        command,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    if result.returncode != 0:
        raise RuntimeError(
            f"native conformance command failed ({result.returncode}): {command}"
        )


def find_cpp_conformance(build_dir):
    suffix = ".exe" if sys.platform == "win32" else ""
    name = f"rti_demo_ui_native_real_conformance{suffix}"
    matches = [
        path
        for path in build_dir.rglob(name)
        if path.is_file() and "CMakeFiles" not in path.parts
    ]
    if len(matches) != 1:
        raise RuntimeError(f"expected one C++ conformance executable, found {matches}")
    return matches[0]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--static-root", required=True, type=Path)
    args = parser.parse_args()

    build_dir = args.build_dir.resolve()
    static_root = args.static_root.resolve()
    cpp_conformance = find_cpp_conformance(build_dir)

    environment = dict(os.environ)
    run([str(cpp_conformance)], environment=environment)

    if sys.platform in {"darwin", "win32"}:
        python_conformance = Path(__file__).with_name("real_conformance.py")
        run(
            [
                sys.executable,
                str(python_conformance),
                "--static-root",
                str(static_root),
            ],
            environment=environment,
        )


if __name__ == "__main__":
    main()
