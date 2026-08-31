cmake_minimum_required(VERSION 3.16)
project(rti_demo_ui_docs NONE)

find_package(Doxygen REQUIRED)
find_package(Python3 3.11 REQUIRED COMPONENTS Interpreter)

set(RTI_DEMO_UI_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/..")
set(RTI_DEMO_UI_DOXYGEN_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/doxygen")
set(RTI_DEMO_UI_DOXYGEN_XML "${RTI_DEMO_UI_DOXYGEN_OUTPUT}/xml")
set(RTI_DEMO_UI_SPHINX_OUTPUT "${CMAKE_CURRENT_BINARY_DIR}/html")

configure_file(Doxyfile.in Doxyfile @ONLY)

file(GLOB_RECURSE RTI_DEMO_UI_CPP_HEADERS CONFIGURE_DEPENDS
    "${RTI_DEMO_UI_ROOT}/cpp/include/rti_demo_ui/*.hpp"
)
file(GLOB_RECURSE RTI_DEMO_UI_PYTHON_SOURCES CONFIGURE_DEPENDS
    "${RTI_DEMO_UI_ROOT}/python/rti_demo_ui/*.py"
)
file(GLOB_RECURSE RTI_DEMO_UI_DOC_SOURCES CONFIGURE_DEPENDS
    "${CMAKE_CURRENT_SOURCE_DIR}/*.md"
    "${CMAKE_CURRENT_SOURCE_DIR}/*.py"
    "${CMAKE_CURRENT_SOURCE_DIR}/*.rst"
)

set(RTI_DEMO_UI_DOXYGEN_INDEX
    "${RTI_DEMO_UI_DOXYGEN_XML}/index.xml"
)

add_custom_command(
    OUTPUT "${RTI_DEMO_UI_DOXYGEN_INDEX}"
    COMMAND Doxygen::doxygen "${CMAKE_CURRENT_BINARY_DIR}/Doxyfile"
    DEPENDS
        "${CMAKE_CURRENT_BINARY_DIR}/Doxyfile"
        ${RTI_DEMO_UI_CPP_HEADERS}
    COMMENT "Generating C++ API XML with Doxygen"
    VERBATIM
)

add_custom_target(doxygen_xml DEPENDS "${RTI_DEMO_UI_DOXYGEN_INDEX}")

add_custom_target(docs
    COMMAND
        "${CMAKE_COMMAND}" -E env
        "RTI_DEMO_UI_DOXYGEN_XML=${RTI_DEMO_UI_DOXYGEN_XML}"
        "${Python3_EXECUTABLE}" -m sphinx
        -W
        --keep-going
        -b html
        "${CMAKE_CURRENT_SOURCE_DIR}"
        "${RTI_DEMO_UI_SPHINX_OUTPUT}"
    COMMAND
        "${Python3_EXECUTABLE}"
        "${CMAKE_CURRENT_SOURCE_DIR}/check_api_reference.py"
        "${RTI_DEMO_UI_SPHINX_OUTPUT}"
    DEPENDS
        doxygen_xml
        ${RTI_DEMO_UI_DOC_SOURCES}
        ${RTI_DEMO_UI_PYTHON_SOURCES}
    COMMENT "Building HTML documentation with Sphinx"
    VERBATIM
)
