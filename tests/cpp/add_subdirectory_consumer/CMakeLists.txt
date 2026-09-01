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
project(rti_demo_ui_parent_version_test VERSION 9.8.7 LANGUAGES CXX)

if(NOT RTI_DEMO_UI_SOURCE_DIR)
    message(FATAL_ERROR "RTI_DEMO_UI_SOURCE_DIR is required")
endif()

set(BUILD_TESTING OFF)
add_subdirectory("${RTI_DEMO_UI_SOURCE_DIR}/cpp" core)

get_target_property(RTI_DEMO_UI_ACTUAL_VERSION rti_demo_ui::core VERSION)
if(NOT RTI_DEMO_UI_ACTUAL_VERSION STREQUAL "0.4.1")
    message(FATAL_ERROR
        "rti_demo_ui::core version is ${RTI_DEMO_UI_ACTUAL_VERSION}, expected 0.4.1"
    )
endif()
