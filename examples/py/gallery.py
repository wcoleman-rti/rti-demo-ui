"""Gallery example: serves the shared /gallery asset. See
docs/architecture.md §10.4.
"""

from rti_demo_gui_sdk import CoreApp


def main() -> None:
    app = CoreApp(title="Gallery")
    # "/" is intentionally blank here: this example adds no cards, so the
    # widget gallery only lives at "/gallery" (see docs/architecture.md §10.4).
    print(
        "Open http://localhost:8080/gallery in your browser to view the widget gallery."
    )
    app.run()


if __name__ == "__main__":
    main()
