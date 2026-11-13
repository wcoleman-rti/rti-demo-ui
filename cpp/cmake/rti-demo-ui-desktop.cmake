# (c) 2026 Copyright, Real-Time Innovations, Inc. All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software. Licensee has the right to distribute object form
# only for use with RTI products. The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software. RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.

include_guard(GLOBAL)

function(rti_demo_ui_install_desktop_app)
    if(NOT CMAKE_SYSTEM_NAME STREQUAL "Linux")
        message(FATAL_ERROR "rti_demo_ui_install_desktop_app requires Linux")
    endif()
    cmake_parse_arguments(PARSE_ARGV 0 app ""
        "TARGET;APPLICATION_ID;NAME;ICON" "")
    if(app_UNPARSED_ARGUMENTS OR app_KEYWORDS_MISSING_VALUES)
        message(FATAL_ERROR "Invalid desktop application arguments")
    endif()
    foreach(required TARGET APPLICATION_ID NAME ICON)
        if(NOT DEFINED app_${required} OR app_${required} STREQUAL "")
            message(FATAL_ERROR "Desktop application requires ${required}")
        endif()
    endforeach()
    if(NOT TARGET "${app_TARGET}")
        message(FATAL_ERROR "Desktop application TARGET does not exist")
    endif()
    get_target_property(target_type "${app_TARGET}" TYPE)
    get_target_property(imported "${app_TARGET}" IMPORTED)
    get_target_property(alias "${app_TARGET}" ALIASED_TARGET)
    if(NOT target_type STREQUAL "EXECUTABLE" OR imported OR alias)
        message(FATAL_ERROR "Desktop application TARGET must be a local executable")
    endif()
    if(NOT app_APPLICATION_ID MATCHES
       "^[a-z]([a-z0-9-]*[a-z0-9])?(\\.[a-z]([a-z0-9-]*[a-z0-9])?)+$")
        message(FATAL_ERROR "APPLICATION_ID must be a lowercase reverse-DNS identifier")
    endif()
    get_filename_component(icon "${app_ICON}" ABSOLUTE
        BASE_DIR "${CMAKE_CURRENT_SOURCE_DIR}")
    if(NOT EXISTS "${icon}" OR IS_DIRECTORY "${icon}")
        message(FATAL_ERROR "Desktop application ICON must be an existing image file")
    endif()
    get_filename_component(extension "${icon}" EXT)
    string(TOLOWER "${extension}" extension)
    if(NOT extension MATCHES "^\\.(png|svg|xpm)$")
        message(FATAL_ERROR "Desktop application ICON must be PNG, SVG, or XPM")
    endif()
    include(GNUInstallDirs)
    foreach(value IN ITEMS "${app_NAME}" "${CMAKE_INSTALL_BINDIR}"
                           "${CMAKE_INSTALL_DATADIR}")
        if(value MATCHES "[\n\r\t;]")
            message(FATAL_ERROR "Desktop names and install directories cannot contain control characters or semicolons")
        endif()
    endforeach()
    install(TARGETS "${app_TARGET}" RUNTIME DESTINATION "${CMAKE_INSTALL_BINDIR}")
    install(FILES "${icon}" DESTINATION "${CMAKE_INSTALL_DATADIR}/pixmaps"
        RENAME "${app_APPLICATION_ID}${extension}")

    set(name "${app_NAME}")
    set(id "${app_APPLICATION_ID}")
    set(bindir "${CMAKE_INSTALL_BINDIR}")
    set(datadir "${CMAKE_INSTALL_DATADIR}")
    set(filename "$<TARGET_FILE_NAME:${app_TARGET}>")
    set(output "${CMAKE_CURRENT_BINARY_DIR}/${id}-$<CONFIG>.desktop")
    foreach(variable name id bindir datadir filename output)
        set(delimiter "=")
        while("${${variable}}" MATCHES "\\]${delimiter}\\]")
            string(APPEND delimiter "=")
        endwhile()
        set(${variable}_literal "[${delimiter}[${${variable}}]${delimiter}]")
    endforeach()
    # Resolve runtime paths at install time, without embedding DESTDIR.
    string(CONFIGURE [=[
set(_name @name_literal@)
set(_id @id_literal@)
set(_bindir @bindir_literal@)
set(_datadir @datadir_literal@)
set(_filename @filename_literal@)
set(_output @output_literal@)
if(NOT IS_ABSOLUTE "${_bindir}")
    set(_bindir "${CMAKE_INSTALL_PREFIX}/${_bindir}")
endif()
if(NOT IS_ABSOLUTE "${_datadir}")
    set(_datadir "${CMAKE_INSTALL_PREFIX}/${_datadir}")
endif()
set(_exec "${_bindir}/${_filename}")
if(_exec MATCHES "[%\n\r\t;]")
    message(FATAL_ERROR
        "Desktop executable paths cannot contain percent signs, control characters, or semicolons")
endif()
# Desktop Entry value decoding precedes Exec argument parsing.
string(REPLACE "\\" "\\\\" _exec "${_exec}")
string(REPLACE "\"" "\\\"" _exec "${_exec}")
string(REPLACE "`" "\\`" _exec "${_exec}")
string(REPLACE "$" "\\$" _exec "${_exec}")
string(REPLACE "\\" "\\\\" _exec "${_exec}")
string(REPLACE "\\" "\\\\" _name "${_name}")
file(WRITE "${_output}"
    "[Desktop Entry]\nType=Application\nName=${_name}\nExec=\"${_exec}\"\nIcon=${_id}\nStartupWMClass=${_id}\nTerminal=false\n")
file(INSTALL "${_output}" DESTINATION "${_datadir}/applications"
    TYPE FILE RENAME "${_id}.desktop")
]=] install_code @ONLY)
    install(CODE "${install_code}")
endfunction()
