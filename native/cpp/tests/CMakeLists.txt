add_executable(rti_demo_ui_native_runner_tests runner_tests.cpp)
target_include_directories(rti_demo_ui_native_runner_tests
    PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/../src"
)
target_link_libraries(
    rti_demo_ui_native_runner_tests PRIVATE rti_demo_ui_native::native_webview
)
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
        native_real_engine_smoke PROPERTIES LABELS real_engine TIMEOUT 30
    )
endif()
