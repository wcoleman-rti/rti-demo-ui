"""Opt-in uPlot renderer for the generic RTI Demo UI time-series component."""

from importlib import resources


def enable_uplot(app):
    """Register the locally bundled uPlot renderer on ``app`` before run()."""
    assets = resources.files(__package__).joinpath("_assets")
    app._register_adapter(
        "uplot",
        "1",
        ("timeseries",),
        assets.joinpath("runtime.js").read_bytes(),
        assets.joinpath("theme.css").read_bytes(),
    )


__all__ = ["enable_uplot"]
