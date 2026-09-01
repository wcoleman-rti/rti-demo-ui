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

function(rti_demo_cpp_asset input_var output_var size_var)
    set(asset "${${input_var}}")
    string(LENGTH "${asset}" asset_size)
    set(statements "")
    while(asset_size GREATER 0)
        if(asset_size GREATER 8192)
            set(chunk_size 8192)
        else()
            set(chunk_size "${asset_size}")
        endif()
        string(SUBSTRING "${asset}" 0 "${chunk_size}" chunk)
        string(APPEND statements
            "        result.append(R\"RTI_ASSET(${chunk})RTI_ASSET\");\n"
        )
        string(SUBSTRING "${asset}" "${chunk_size}" -1 asset)
        string(LENGTH "${asset}" asset_size)
    endwhile()
    set("${output_var}" "${statements}" PARENT_SCOPE)
    string(LENGTH "${${input_var}}" total_size)
    set("${size_var}" "${total_size}" PARENT_SCOPE)
endfunction()

foreach(asset_var
        RTI_DEMO_INDEX_HTML
        RTI_DEMO_RUNTIME_JS
        RTI_DEMO_RUNTIME3D_JS
        RTI_DEMO_CLIENT_JS
        RTI_DEMO_THEME_CSS)
    string(FIND "${${asset_var}}" "RTI_ASSET" RTI_DEMO_ASSET_DELIMITER_INDEX)
    if(NOT RTI_DEMO_ASSET_DELIMITER_INDEX EQUAL -1)
        message(FATAL_ERROR "${asset_var} contains the reserved raw-string delimiter RTI_ASSET")
    endif()
endforeach()

rti_demo_cpp_asset(
    RTI_DEMO_INDEX_HTML RTI_DEMO_INDEX_HTML_CPP RTI_DEMO_INDEX_HTML_SIZE
)
rti_demo_cpp_asset(
    RTI_DEMO_RUNTIME_JS RTI_DEMO_RUNTIME_JS_CPP RTI_DEMO_RUNTIME_JS_SIZE
)
rti_demo_cpp_asset(
    RTI_DEMO_RUNTIME3D_JS RTI_DEMO_RUNTIME3D_JS_CPP RTI_DEMO_RUNTIME3D_JS_SIZE
)
rti_demo_cpp_asset(
    RTI_DEMO_CLIENT_JS RTI_DEMO_CLIENT_JS_CPP RTI_DEMO_CLIENT_JS_SIZE
)
rti_demo_cpp_asset(
    RTI_DEMO_THEME_CSS RTI_DEMO_THEME_CSS_CPP RTI_DEMO_THEME_CSS_SIZE
)

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
set_target_properties(rti_demo_ui_core PROPERTIES VERSION 0.4.0)

target_include_directories(rti_demo_ui_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE
        "${CMAKE_CURRENT_BINARY_DIR}/generated"
)

target_link_libraries(rti_demo_ui_core
    PUBLIC httplib::httplib nlohmann_json::nlohmann_json
)

add_library(rti_demo_ui::core ALIAS rti_demo_ui_core)

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
