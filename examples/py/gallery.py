"""Gallery example: serves an application-owned static root."""

import asyncio
from pathlib import Path

from rti_demo_ui import DemoUiApp


async def main() -> None:
    static_root = Path(__file__).resolve().parents[1] / "web" / "gallery"
    app = DemoUiApp(title="Gallery", static_root=static_root)
    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
