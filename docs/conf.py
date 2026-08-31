"""Sphinx configuration for the RTI Demo UI documentation."""

from __future__ import annotations

import os
from pathlib import Path


project = "RTI Demo UI"
copyright = "2026, Real-Time Innovations, Inc."

extensions = [
    "breathe",
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
]

source_suffix = {
    ".md": "markdown",
}
exclude_patterns = [
    "_build",
    "development/implementation-plans",
]

myst_enable_extensions = [
    "colon_fence",
]
myst_heading_anchors = 4

autodoc_member_order = "bysource"
autodoc_typehints = "description"

doxygen_xml = os.environ.get(
    "RTI_DEMO_UI_DOXYGEN_XML",
    str(Path(__file__).parent / "_build" / "doxygen" / "xml"),
)
breathe_projects = {
    "rti_demo_ui": doxygen_xml,
}
breathe_default_project = "rti_demo_ui"
breathe_default_members = ("members",)

html_theme = "furo"
html_title = "RTI Demo UI"
html_static_path = []
