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

from pathlib import Path
from shutil import copy2

from setuptools.command.build_py import build_py as _build_py


class build_py(_build_py):
    def run(self):
        super().run()
        source_root = Path(__file__).parent / "assets"
        destination_root = Path(self.build_lib) / "rti_demo_ui" / "_assets"
        destination_root.mkdir(parents=True, exist_ok=True)
        for source in source_root.iterdir():
            if source.is_file():
                copy2(source, destination_root / source.name)
