// Gallery example: serves the shared /gallery asset (see
// docs/architecture.md §10.4).
#include <iostream>
#include <rti_demo_gui_sdk/gui_sdk.hpp>

int main() {
    rti_demo_gui_sdk::CoreApp app("Gallery");
    // "/" is intentionally blank here: this example adds no cards, so the
    // widget gallery only lives at "/gallery".
    std::cout << "Open http://localhost:8080/gallery in your browser to view "
                 "the widget gallery."
              << std::endl;
    app.run();
    return 0;
}
