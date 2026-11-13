set(RTI_DEMO_UPLOT_ASSETS_DIR "${CMAKE_CURRENT_LIST_DIR}/../assets")
set(RTI_DEMO_UPLOT_ASSET_FILES
    "${RTI_DEMO_UPLOT_ASSETS_DIR}/runtime.js"
    "${RTI_DEMO_UPLOT_ASSETS_DIR}/theme.css"
)
set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS
    ${RTI_DEMO_UPLOT_ASSET_FILES}
)
foreach(asset_file ${RTI_DEMO_UPLOT_ASSET_FILES})
    if(NOT EXISTS "${asset_file}")
        message(FATAL_ERROR "uPlot adapter asset not found: ${asset_file}")
    endif()
endforeach()

file(READ "${RTI_DEMO_UPLOT_ASSETS_DIR}/runtime.js" RTI_UPLOT_RUNTIME_JS)
file(READ "${RTI_DEMO_UPLOT_ASSETS_DIR}/theme.css" RTI_UPLOT_THEME_CSS)
foreach(asset_var RTI_UPLOT_RUNTIME_JS RTI_UPLOT_THEME_CSS)
    string(FIND "${${asset_var}}" "RTI_UPLOT_ASSET" delimiter_index)
    if(NOT delimiter_index EQUAL -1)
        message(FATAL_ERROR "${asset_var} contains the reserved C++ asset delimiter")
    endif()
endforeach()

function(rti_demo_uplot_asset input_var output_var size_var)
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
            "        result.append(R\"RTI_UPLOT_ASSET(${chunk})RTI_UPLOT_ASSET\");\n"
        )
        string(SUBSTRING "${asset}" "${chunk_size}" -1 asset)
        string(LENGTH "${asset}" asset_size)
    endwhile()
    set("${output_var}" "${statements}" PARENT_SCOPE)
    string(LENGTH "${${input_var}}" total_size)
    set("${size_var}" "${total_size}" PARENT_SCOPE)
endfunction()

rti_demo_uplot_asset(
    RTI_UPLOT_RUNTIME_JS RTI_UPLOT_RUNTIME_JS_CPP RTI_UPLOT_RUNTIME_JS_SIZE
)
rti_demo_uplot_asset(
    RTI_UPLOT_THEME_CSS RTI_UPLOT_THEME_CSS_CPP RTI_UPLOT_THEME_CSS_SIZE
)
file(MAKE_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated")
configure_file(
    "${CMAKE_CURRENT_LIST_DIR}/src/uplot_assets.hpp.in"
    "${CMAKE_CURRENT_BINARY_DIR}/generated/uplot_assets.hpp"
    @ONLY
)

add_library(rti_demo_ui_uplot STATIC src/uplot_adapter.cpp)
set_target_properties(rti_demo_ui_uplot PROPERTIES EXPORT_NAME uplot)
target_compile_features(rti_demo_ui_uplot PUBLIC cxx_std_17)
target_include_directories(rti_demo_ui_uplot
    PUBLIC
        $<BUILD_INTERFACE:${CMAKE_CURRENT_LIST_DIR}/include>
        $<INSTALL_INTERFACE:include>
    PRIVATE "${CMAKE_CURRENT_BINARY_DIR}/generated"
)
target_link_libraries(rti_demo_ui_uplot PUBLIC rti_demo_ui_core)
add_library(rti_demo_ui::uplot ALIAS rti_demo_ui_uplot)

install(
    TARGETS rti_demo_ui_uplot
    EXPORT rti_demo_ui_targets
    ARCHIVE DESTINATION ${CMAKE_INSTALL_LIBDIR}
)
install(
    DIRECTORY include/rti_demo_ui
    DESTINATION ${CMAKE_INSTALL_INCLUDEDIR}
)
install(
    FILES "${RTI_DEMO_UPLOT_ASSETS_DIR}/LICENSE-uPlot"
    DESTINATION ${CMAKE_INSTALL_DATADIR}/rti-demo-ui/licenses
)
