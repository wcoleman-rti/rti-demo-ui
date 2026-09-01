#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.
#

cmake_minimum_required(VERSION 3.16)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

include(FetchContent)
include(GNUInstallDirs)
include(CMakePackageConfigHelpers)
include("${CMAKE_CURRENT_LIST_DIR}/../cmake/rti-demo-ui-version.cmake")

set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZSTD_IF_AVAILABLE OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
    cpp_httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
    GIT_TAG a7bc00e3307fecdb4d67545e93be7b88cfb1e186 # v0.18.3
)
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
    GIT_TAG 9cca280a4d0ccf0c08f47a99aa71d1b0e52f8d03 # v3.11.3
)
FetchContent_MakeAvailable(cpp_httplib nlohmann_json)

set(RTI_DEMO_UI_ASSETS_DIR "${CMAKE_CURRENT_LIST_DIR}/../assets")
set(RTI_DEMO_ASSET_FILES
    "${RTI_DEMO_UI_ASSETS_DIR}/index.html"
    "${RTI_DEMO_UI_ASSETS_DIR}/runtime.js"
    "${RTI_DEMO_UI_ASSETS_DIR}/runtime3d.js"
    "${RTI_DEMO_UI_ASSETS_DIR}/client.js"
    "${RTI_DEMO_UI_ASSETS_DIR}/theme.css"
)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${RTI_DEMO_ASSET_FILES}
)
foreach(asset_file ${RTI_DEMO_ASSET_FILES})
    if(NOT EXISTS "${asset_file}")
        message(FATAL_ERROR "RTI Demo UI asset not found: ${asset_file}")
    endif()
endforeach()

file(READ "${RTI_DEMO_UI_ASSETS_DIR}/index.html" RTI_DEMO_INDEX_HTML)
file(READ "${RTI_DEMO_UI_ASSETS_DIR}/runtime.js" RTI_DEMO_RUNTIME_JS)
file(READ "${RTI_DEMO_UI_ASSETS_DIR}/runtime3d.js" RTI_DEMO_RUNTIME3D_JS)
file(READ "${RTI_DEMO_UI_ASSETS_DIR}/client.js" RTI_DEMO_CLIENT_JS)
file(READ "${RTI_DEMO_UI_ASSETS_DIR}/theme.css" RTI_DEMO_THEME_CSS)

foreach(asset_var RTI_DEMO_INDEX_HTML RTI_DEMO_RUNTIME_JS RTI_DEMO_RUNTIME3D_JS RTI_DEMO_CLIENT_JS RTI_DEMO_THEME_CSS)
    string(FIND "${${asset_var}}" "RTI_ASSET" RTI_DEMO_ASSET_DELIMITER_INDEX)
    if(NOT RTI_DEMO_ASSET_DELIMITER_INDEX EQUAL -1)
        message(FATAL_ERROR "${asset_var} contains the reserved raw-string delimiter RTI_ASSET")
    endif()
endforeach()

file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
configure_file(
    src/web_assets.hpp.in
    "${CMAKE_CURRENT_BINARY_DIR}/generated/web_assets.hpp"
    @ONLY
)

add_library(rti_demo_ui_core STATIC
    src/demo_ui_app.cpp
    src/components.cpp
)
set_target_properties(
    rti_demo_ui_core PROPERTIES
    EXPORT_NAME core
    VERSION ${RTI_DEMO_UI_VERSION}
)

target_include_directories(rti_demo_ui_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<BUILD_INTERFACE:${cpp_httplib_SOURCE_DIR}>
        $<BUILD_INTERFACE:${nlohmann_json_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE
        "${CMAKE_CURRENT_BINARY_DIR}/generated"
)

add_library(rti_demo_ui::core ALIAS rti_demo_ui_core)

install(
    TARGETS rti_demo_ui_core
    EXPORT rti_demo_ui_targets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(
    DIRECTORY include/rti_demo_ui
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
install(
    FILES "${cpp_httplib_SOURCE_DIR}/httplib.h"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
install(
    DIRECTORY "${nlohmann_json_SOURCE_DIR}/include/nlohmann"
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
install(
    FILES "${CMAKE_CURRENT_LIST_DIR}/../LICENSE"
    DESTINATION ${CMAKE_INSTALL_DATADIR}/rti-demo-ui/licenses
    RENAME LICENSE-rti-demo-ui
)
install(
    FILES "${cpp_httplib_SOURCE_DIR}/LICENSE"
    DESTINATION ${CMAKE_INSTALL_DATADIR}/rti-demo-ui/licenses
    RENAME LICENSE-cpp-httplib
)
install(
    FILES "${nlohmann_json_SOURCE_DIR}/LICENSE.MIT"
    DESTINATION ${CMAKE_INSTALL_DATADIR}/rti-demo-ui/licenses
    RENAME LICENSE-nlohmann-json
)
install(
    FILES "${CMAKE_CURRENT_LIST_DIR}/../README.md"
    DESTINATION ${CMAKE_INSTALL_DATADIR}/rti-demo-ui
)

set(RTI_DEMO_UI_CMAKE_INSTALL_DIR
    "${CMAKE_INSTALL_LIBDIR}/cmake/rti_demo_ui"
)
configure_package_config_file(
    "${CMAKE_CURRENT_LIST_DIR}/cmake/rti-demo-ui-config.cmake.in"
    "${CMAKE_CURRENT_BINARY_DIR}/rti_demo_ui-config.cmake"
    INSTALL_DESTINATION "${RTI_DEMO_UI_CMAKE_INSTALL_DIR}"
)
write_basic_package_version_file(
    "${CMAKE_CURRENT_BINARY_DIR}/rti_demo_ui-config-version.cmake"
    VERSION "${RTI_DEMO_UI_VERSION}"
    COMPATIBILITY SameMajorVersion
)
install(
    EXPORT rti_demo_ui_targets
    FILE rti_demo_ui-targets.cmake
    NAMESPACE rti_demo_ui::
    DESTINATION "${RTI_DEMO_UI_CMAKE_INSTALL_DIR}"
)
install(
    FILES
        "${CMAKE_CURRENT_BINARY_DIR}/rti_demo_ui-config.cmake"
        "${CMAKE_CURRENT_BINARY_DIR}/rti_demo_ui-config-version.cmake"
    DESTINATION "${RTI_DEMO_UI_CMAKE_INSTALL_DIR}"
)

if(NOT DEFINED RTI_DEMO_TOP_LEVEL_BUILD)
    if(CMAKE_SOURCE_DIR STREQUAL CMAKE_CURRENT_SOURCE_DIR)
        set(RTI_DEMO_TOP_LEVEL_BUILD ON)
    else()
        set(RTI_DEMO_TOP_LEVEL_BUILD OFF)
    endif()
endif()

option(RTI_DEMO_BUILD_EXAMPLES "Build SDK examples" ${RTI_DEMO_TOP_LEVEL_BUILD})

if(RTI_DEMO_BUILD_EXAMPLES)
    add_subdirectory(
        "${CMAKE_CURRENT_SOURCE_DIR}/../examples/cpp"
        "${CMAKE_CURRENT_BINARY_DIR}/examples"
    )
endif()

if(BUILD_TESTING AND RTI_DEMO_TOP_LEVEL_BUILD)
    add_subdirectory(
        "${CMAKE_CURRENT_SOURCE_DIR}/../tests/cpp"
        "${CMAKE_CURRENT_BINARY_DIR}/tests"
    )
endif()
