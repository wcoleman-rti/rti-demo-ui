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

import os
from pathlib import Path
from shutil import copy2

from setuptools.command.build_py import build_py as _build_py
from setuptools.command.editable_wheel import editable_wheel as _editable_wheel


class build_py(_build_py):
    def run(self):
        super().run()
        source_root = Path(__file__).parents[1] / "assets"
        destination_root = Path(self.build_lib) / "rti_demo_ui" / "_assets"
        destination_root.mkdir(parents=True, exist_ok=True)
        for source in source_root.iterdir():
            if source.is_file():
                copy2(source, destination_root / source.name)


class editable_wheel(_editable_wheel):
    def run(self):
        super().run()
        source_root = Path(__file__).parents[1] / "assets"
        destination = Path(__file__).parent / "rti_demo_ui" / "_assets"
        if not destination.exists() and not destination.is_symlink():
            relative_source = os.path.relpath(source_root, destination.parent)
            destination.symlink_to(relative_source, target_is_directory=True)
