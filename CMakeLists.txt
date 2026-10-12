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
include(cmake/rti-demo-ui-version.cmake)
project(rti_demo_ui VERSION ${RTI_DEMO_UI_VERSION} LANGUAGES CXX)

include(CTest)
set(RTI_DEMO_TOP_LEVEL_BUILD ON)
option(RTI_DEMO_BUILD_NATIVE_WEBVIEW
       "Build the optional native webview companion" OFF)

add_subdirectory(cpp)

if(RTI_DEMO_BUILD_NATIVE_WEBVIEW)
    add_subdirectory(native/cpp native)
endif()
