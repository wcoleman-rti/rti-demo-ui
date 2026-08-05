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
