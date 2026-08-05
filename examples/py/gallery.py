"""Gallery example: serves an application-owned static root."""

from pathlib import Path

from rti_demo_ui import DemoUiApp


def main() -> None:
    static_root = Path(__file__).resolve().parents[1] / "web" / "gallery"
    app = DemoUiApp(title="Gallery", static_root=static_root)
    print("Open http://localhost:8080/ in your browser to view the widget gallery.")
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
