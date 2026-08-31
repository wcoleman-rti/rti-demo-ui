"""Gallery example: serves an application-owned static root."""

import asyncio
import argparse
from pathlib import Path

from rti_demo_ui import CardArea, DemoUiApp, Layout, Theme


def parse_args():
    parser = argparse.ArgumentParser(description="Run the RTI Demo UI gallery")
    parser.add_argument(
        "--theme", choices=[theme.value for theme in Theme], default=Theme.dark.value
    )
    parser.add_argument(
        "--layout",
        choices=[layout.value for layout in Layout],
        default=Layout.auto.value,
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    static_root = Path(__file__).resolve().parents[1] / "web" / "gallery"
    app = DemoUiApp(
        title="Gallery",
        static_root=static_root,
        theme=args.theme,
        layout=args.layout,
    )
    app.add_card("Presentation", area=CardArea.sidebar).add_text(
        f"{args.theme} / {args.layout}"
    )
    app.add_card("Telemetry", span=2).add_metric("Connected assets", 12)
    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
