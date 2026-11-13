#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of
# the use or inability to use the software.
#

import hashlib
from pathlib import Path


ROOT = Path(__file__).parents[2]
ASSET_ROOT = ROOT / "adapters" / "uplot"


def test_generated_uplot_assets_match_the_recorded_checksums_and_python_copy():
    records = {}
    for line in (ASSET_ROOT / "assets.sha256").read_text().splitlines():
        digest, path = line.split(maxsplit=1)
        records[path.removeprefix("assets/")] = digest
    for name in ("runtime.js", "theme.css", "LICENSE-uPlot"):
        data = (ASSET_ROOT / "assets" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == records[name]
        assert (
            data
            == (
                ASSET_ROOT
                / "python"
                / "src"
                / "rti_demo_ui_adapter_uplot"
                / "_assets"
                / name
            ).read_bytes()
        )
