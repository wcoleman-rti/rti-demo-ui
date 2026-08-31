add_executable(rti_demo_ui_native_dual_mode dual_mode.cpp)
target_link_libraries(
    rti_demo_ui_native_dual_mode PRIVATE rti_demo_ui_native::native_webview
)
