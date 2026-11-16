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

function(run)
    execute_process(COMMAND ${ARGV} RESULT_VARIABLE result
        OUTPUT_VARIABLE output ERROR_VARIABLE error)
    if(NOT result STREQUAL "0")
        message(FATAL_ERROR "Command failed (${result}): ${ARGV}\n${output}\n${error}")
    endif()
endfunction()

set(build "${TEST_ROOT}/build")
set(prefix "${TEST_ROOT}/installed prefix")
set(stage "${TEST_ROOT}/stage")
run("${CMAKE_COMMAND}" -S "${TEST_SOURCE}" -B "${build}"
    -G "${TEST_GENERATOR}"
    "-DDESKTOP_MODULE=${DESKTOP_MODULE}"
    "-DCMAKE_INSTALL_PREFIX=${TEST_ROOT}/unused-prefix"
    "-DCMAKE_INSTALL_BINDIR=libexec/app tools"
    "-DCMAKE_INSTALL_DATADIR=share/app data")
run("${CMAKE_COMMAND}" --build "${build}" --config Release)
run("${CMAKE_COMMAND}" -E env "DESTDIR=${stage}"
    "${CMAKE_COMMAND}" --install "${build}" --config Release --prefix "${prefix}")
set(desktop "${stage}${prefix}/share/app data/applications/com.example.desktop-probe.desktop")
set(icon "${stage}${prefix}/share/app data/pixmaps/com.example.desktop-probe.svg")
if(NOT EXISTS "${desktop}" OR NOT EXISTS "${icon}")
    message(FATAL_ERROR "Desktop entry or icon missing from staged installation")
endif()
file(READ "${desktop}" contents)
string(FIND "${contents}"
    "Exec=\"${prefix}/libexec/app tools/desktop_probe\"\n" exec_position)
string(FIND "${contents}" "Icon=com.example.desktop-probe\n" icon_position)
string(FIND "${contents}" "StartupWMClass=com.example.desktop-probe\n" class_position)
if(exec_position LESS 0 OR icon_position LESS 0 OR class_position LESS 0 OR
   contents MATCHES "${stage}|unused-prefix")
    message(FATAL_ERROR "Incorrect installed desktop entry:\n${contents}")
endif()
run("${stage}${prefix}/libexec/app tools/desktop_probe")

execute_process(
    COMMAND "${CMAKE_COMMAND}" -E env "DESTDIR=${stage}"
        "${CMAKE_COMMAND}" --install "${build}" --config Release
        --prefix "${TEST_ROOT}/invalid%prefix"
    RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error)
if(result STREQUAL "0" OR NOT error MATCHES "percent signs")
    message(FATAL_ERROR "Unsupported executable path was not rejected:\n${output}\n${error}")
endif()

foreach(invalid APPLICATION_ID ICON)
    if(invalid STREQUAL "APPLICATION_ID")
        set(value "not a desktop identity")
        set(expected "reverse-DNS")
    else()
        set(value "${TEST_ROOT}/missing.png")
        set(expected "existing image")
    endif()
    execute_process(
        COMMAND "${CMAKE_COMMAND}" -S "${TEST_SOURCE}" -B "${TEST_ROOT}/${invalid}"
            "-DDESKTOP_MODULE=${DESKTOP_MODULE}" "-D${invalid}=${value}"
        RESULT_VARIABLE result OUTPUT_VARIABLE output ERROR_VARIABLE error)
    if(result STREQUAL "0" OR NOT error MATCHES "${expected}")
        message(FATAL_ERROR "Invalid ${invalid} was not rejected:\n${output}\n${error}")
    endif()
endforeach()
