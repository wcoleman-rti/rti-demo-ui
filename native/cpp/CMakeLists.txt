cmake_minimum_required(VERSION 3.16)
project(rti_demo_ui_native VERSION 0.4.0 LANGUAGES CXX)

include(CTest)
include(FetchContent)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
option(RTI_DEMO_NATIVE_REAL_ENGINE_TESTS
       "Build real native-window smoke coverage" OFF)
option(RTI_DEMO_NATIVE_BUILD_EXAMPLES
       "Build native companion examples" OFF)

if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
    message(FATAL_ERROR
        "rti_demo_ui_native 0.4 supports only Linux; use browser mode on this platform"
    )
endif()

if(NOT TARGET rti_demo_ui::core)
    set(RTI_DEMO_UI_SOURCE_DIR
        "${CMAKE_CURRENT_LIST_DIR}/../.."
        CACHE PATH "Path to the rti-demo-ui source tree"
    )
    add_subdirectory("${RTI_DEMO_UI_SOURCE_DIR}/cpp" core-build)
endif()
get_target_property(RTI_DEMO_UI_CORE_VERSION rti_demo_ui::core VERSION)
if(NOT RTI_DEMO_UI_CORE_VERSION MATCHES "^0\\.4\\.")
    message(FATAL_ERROR
        "rti_demo_ui_native 0.4 requires an rti_demo_ui::core 0.4.x target"
    )
endif()

set(WEBVIEW_WEBKITGTK_API 4.1 CACHE STRING "" FORCE)
set(WEBVIEW_BUILD_SHARED_LIBRARY OFF CACHE BOOL "" FORCE)
set(WEBVIEW_BUILD_STATIC_LIBRARY OFF CACHE BOOL "" FORCE)
FetchContent_Declare(
    webview
    GIT_REPOSITORY https://github.com/webview/webview.git
    GIT_TAG 3ab4b5d722438fc8a13e6ca830c5e2372d19a01d # 0.12.0
)
FetchContent_MakeAvailable(webview)

add_library(rti_demo_ui_native_webview STATIC
    src/control_posix.cpp
    src/native_webview_linux.cpp
    src/navigation.cpp
    src/runner.cpp
)
set_target_properties(
    rti_demo_ui_native_webview PROPERTIES
    NO_SYSTEM_FROM_IMPORTED ON
    VERSION ${PROJECT_VERSION}
)
target_include_directories(rti_demo_ui_native_webview
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE
        "${CMAKE_CURRENT_SOURCE_DIR}/src"
)
target_link_libraries(rti_demo_ui_native_webview
    PUBLIC rti_demo_ui::core
    PRIVATE webview::core
)

add_library(
    rti_demo_ui_native::native_webview ALIAS rti_demo_ui_native_webview
)

if(BUILD_TESTING AND CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
    add_subdirectory(tests)
endif()
if(RTI_DEMO_NATIVE_BUILD_EXAMPLES)
    add_subdirectory(examples)
endif()
