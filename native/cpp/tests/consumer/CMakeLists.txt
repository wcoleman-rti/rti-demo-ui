cmake_minimum_required(VERSION 3.16)
project(rti_demo_ui_native_consumer LANGUAGES CXX)

if(NOT RTI_DEMO_UI_SOURCE_DIR)
    message(FATAL_ERROR "RTI_DEMO_UI_SOURCE_DIR is required")
endif()

set(RTI_DEMO_TOP_LEVEL_BUILD OFF)
set(BUILD_TESTING OFF)
add_subdirectory("${RTI_DEMO_UI_SOURCE_DIR}/cpp" core)
add_subdirectory("${RTI_DEMO_UI_SOURCE_DIR}/native/cpp" native)

add_executable(rti_demo_ui_native_consumer main.cpp)
target_link_libraries(
    rti_demo_ui_native_consumer PRIVATE rti_demo_ui_native::native_webview
)
