cmake_minimum_required(VERSION 3.16)
project(rti_demo_ui_native_webview_spike LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)

set(BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(RTI_DEMO_BUILD_EXAMPLES OFF CACHE BOOL "" FORCE)
add_subdirectory("${CMAKE_CURRENT_LIST_DIR}/../.." core-build)

add_executable(native_webview_cpp_lifecycle cpp_lifecycle.cpp)
target_link_libraries(native_webview_cpp_lifecycle PRIVATE rti_demo_ui::core)

option(NATIVE_WEBVIEW_SPIKE_BUILD_REAL_HOST
       "Build the webview 0.12.0 real-engine host" OFF)
if(NATIVE_WEBVIEW_SPIKE_BUILD_REAL_HOST)
    set(WEBVIEW_WEBKITGTK_API 4.1 CACHE STRING "" FORCE)
    FetchContent_Declare(
        webview
        GIT_REPOSITORY https://github.com/webview/webview.git
        GIT_TAG 3ab4b5d722438fc8a13e6ca830c5e2372d19a01d # 0.12.0
    )
    FetchContent_MakeAvailable(webview)

    add_executable(native_webview_cpp_host cpp_host.cpp)
    target_link_libraries(
        native_webview_cpp_host PRIVATE rti_demo_ui::core webview::core
    )
    target_compile_definitions(
        native_webview_cpp_host PRIVATE
        SPIKE_STATIC_ROOT="${CMAKE_CURRENT_LIST_DIR}/conformance"
    )
endif()
