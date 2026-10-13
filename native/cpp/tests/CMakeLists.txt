add_executable(rti_demo_ui_native_runner_tests runner_tests.cpp)
target_include_directories(rti_demo_ui_native_runner_tests
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../src"
)
target_link_libraries(
    rti_demo_ui_native_runner_tests PRIVATE rti_demo_ui_native::native_webview
)
if(WIN32)
    target_link_libraries(rti_demo_ui_native_runner_tests PRIVATE ws2_32)
endif()
add_test(NAME native_runner_tests COMMAND rti_demo_ui_native_runner_tests)
set_tests_properties(native_runner_tests PROPERTIES TIMEOUT 15)

if(RTI_DEMO_NATIVE_REAL_ENGINE_TESTS)
    add_executable(rti_demo_ui_native_real_smoke real_host_smoke.cpp)
    target_link_libraries(
        rti_demo_ui_native_real_smoke PRIVATE
        rti_demo_ui_native::native_webview
    )
    add_test(
        NAME native_real_engine_smoke
        COMMAND rti_demo_ui_native_real_smoke
    )
    set_tests_properties(
        native_real_engine_smoke PROPERTIES LABELS real_engine TIMEOUT 60
    )

    if(CMAKE_SYSTEM_NAME STREQUAL "Linux")
        find_package(PkgConfig REQUIRED)
        pkg_check_modules(GTK3 REQUIRED IMPORTED_TARGET gtk+-3.0)
        add_executable(rti_demo_ui_native_real_window_size
            real_window_size_linux.cpp
        )
        target_link_libraries(
            rti_demo_ui_native_real_window_size PRIVATE
            rti_demo_ui_native::native_webview
            PkgConfig::GTK3
        )
        add_test(
            NAME native_real_window_size
            COMMAND rti_demo_ui_native_real_window_size
        )
        set_tests_properties(
            native_real_window_size PROPERTIES LABELS real_engine TIMEOUT 60
        )
    endif()

    add_executable(rti_demo_ui_native_real_conformance real_conformance.cpp)
    target_compile_definitions(
        rti_demo_ui_native_real_conformance PRIVATE
        NATIVE_CONFORMANCE_STATIC_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../../../tests/fixtures/native_webview_conformance"
    )
    target_link_libraries(
        rti_demo_ui_native_real_conformance PRIVATE
        rti_demo_ui_native::native_webview
    )
endif()
