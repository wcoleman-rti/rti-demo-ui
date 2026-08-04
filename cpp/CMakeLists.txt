cmake_minimum_required(VERSION 3.16)
project(rti_demo_gui_sdk_core LANGUAGES CXX)

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

set(RTI_DEMO_ASSETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/../assets")
set(RTI_DEMO_ASSET_FILES
    "${RTI_DEMO_ASSETS_DIR}/index.html"
    "${RTI_DEMO_ASSETS_DIR}/runtime.js"
    "${RTI_DEMO_ASSETS_DIR}/theme.css"
    "${RTI_DEMO_ASSETS_DIR}/gallery.html"
)
foreach(asset_file ${RTI_DEMO_ASSET_FILES})
    if(NOT EXISTS "${asset_file}")
        message(FATAL_ERROR "RTI Demo GUI SDK asset not found: ${asset_file}")
    endif()
endforeach()

file(READ "${RTI_DEMO_ASSETS_DIR}/index.html" RTI_DEMO_INDEX_HTML)
file(READ "${RTI_DEMO_ASSETS_DIR}/runtime.js" RTI_DEMO_RUNTIME_JS)
file(READ "${RTI_DEMO_ASSETS_DIR}/theme.css" RTI_DEMO_THEME_CSS)
file(READ "${RTI_DEMO_ASSETS_DIR}/gallery.html" RTI_DEMO_GALLERY_HTML)

foreach(asset_var RTI_DEMO_INDEX_HTML RTI_DEMO_RUNTIME_JS RTI_DEMO_THEME_CSS RTI_DEMO_GALLERY_HTML)
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

add_library(rti_demo_gui_sdk_core STATIC
    src/app.cpp
    src/components.cpp
)

target_include_directories(rti_demo_gui_sdk_core
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE
        "${CMAKE_CURRENT_BINARY_DIR}/generated"
)

target_link_libraries(rti_demo_gui_sdk_core
    PUBLIC httplib::httplib
    PRIVATE nlohmann_json::nlohmann_json
)

add_library(rti_demo_gui_sdk::core ALIAS rti_demo_gui_sdk_core)

if(CMAKE_SOURCE_DIR STREQUAL PROJECT_SOURCE_DIR)
    option(RTI_DEMO_BUILD_EXAMPLES "Build SDK examples" ON)
    include(CTest)
else()
    option(RTI_DEMO_BUILD_EXAMPLES "Build SDK examples" OFF)
endif()

if(RTI_DEMO_BUILD_EXAMPLES)
    add_subdirectory(
        "${CMAKE_CURRENT_SOURCE_DIR}/../examples/cpp"
        "${CMAKE_CURRENT_BINARY_DIR}/examples"
    )
endif()

if(BUILD_TESTING AND CMAKE_SOURCE_DIR STREQUAL PROJECT_SOURCE_DIR)
    add_subdirectory(
        "${CMAKE_CURRENT_SOURCE_DIR}/../tests/cpp"
        "${CMAKE_CURRENT_BINARY_DIR}/tests"
    )
endif()
