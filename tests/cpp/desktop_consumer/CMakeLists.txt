# (c) 2026 Copyright, Real-Time Innovations, Inc. All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software. Licensee has the right to distribute object form
# only for use with RTI products. The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software. RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.

cmake_minimum_required(VERSION 3.16)
project(desktop_consumer LANGUAGES CXX)

if(DESKTOP_MODULE)
    include("${DESKTOP_MODULE}")
else()
    find_package(rti_demo_ui CONFIG REQUIRED)
endif()
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/main.cpp" "int main() { return 0; }\n")
file(WRITE "${CMAKE_CURRENT_BINARY_DIR}/icon.svg"
    "<svg xmlns=\"http://www.w3.org/2000/svg\" width=\"64\" height=\"64\"><rect width=\"64\" height=\"64\" fill=\"red\"/></svg>\n")
add_executable(desktop_probe "${CMAKE_CURRENT_BINARY_DIR}/main.cpp")
if(NOT DEFINED APPLICATION_ID)
    set(APPLICATION_ID "com.example.desktop-probe")
endif()
if(NOT DEFINED ICON)
    set(ICON "${CMAKE_CURRENT_BINARY_DIR}/icon.svg")
endif()
rti_demo_ui_install_desktop_app(
    TARGET desktop_probe
    APPLICATION_ID "${APPLICATION_ID}"
    NAME "Desktop probe"
    ICON "${ICON}"
)
