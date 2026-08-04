cmake_minimum_required(VERSION 3.16)

add_executable(rti_demo_gui_sdk_component_tests component_tests.cpp)
target_link_libraries(rti_demo_gui_sdk_component_tests PRIVATE rti_demo_gui_sdk::core)
add_test(NAME component_tests COMMAND rti_demo_gui_sdk_component_tests)

add_executable(rti_demo_gui_sdk_http_tests http_tests.cpp)
target_link_libraries(rti_demo_gui_sdk_http_tests PRIVATE rti_demo_gui_sdk::core)
target_compile_definitions(rti_demo_gui_sdk_http_tests PRIVATE
    SOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
add_test(NAME http_tests COMMAND rti_demo_gui_sdk_http_tests)
