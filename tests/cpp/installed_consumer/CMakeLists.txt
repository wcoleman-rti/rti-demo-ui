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
project(rti_demo_ui_installed_consumer LANGUAGES CXX)

find_package(rti_demo_ui CONFIG REQUIRED)

add_executable(rti_demo_ui_installed_consumer main.cpp)
target_link_libraries(
    rti_demo_ui_installed_consumer PRIVATE rti_demo_ui::core
)
