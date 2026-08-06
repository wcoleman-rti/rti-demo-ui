cmake_minimum_required(VERSION 3.16)

add_executable(rti_demo_ui_simple simple.cpp)
target_link_libraries(rti_demo_ui_simple PRIVATE rti_demo_ui::core)

add_executable(rti_demo_ui_gallery gallery.cpp)
target_link_libraries(rti_demo_ui_gallery PRIVATE rti_demo_ui::core)
target_compile_definitions(rti_demo_ui_gallery PRIVATE
    RTI_DEMO_GALLERY_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../web/gallery"
)

add_executable(rti_demo_ui_arm3d arm3d.cpp)
target_link_libraries(rti_demo_ui_arm3d PRIVATE rti_demo_ui::core)
target_compile_definitions(rti_demo_ui_arm3d PRIVATE
    RTI_DEMO_ARM3D_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../web/arm3d"
)

option(BUILD_CONNEXT_EXAMPLE "Build the guarded Connext DDS example" OFF)
if(BUILD_CONNEXT_EXAMPLE)
    include(FetchContent)
    set(RTICONNEXT_CMAKE_UTILS_GIT_TAG
      "2c4b3efef3ed87135565f5d9493303938a76da31"
      CACHE STRING ""
    )
    FetchContent_Declare(
        rticonnextdds_cmake_utils
        GIT_REPOSITORY https://github.com/rticommunity/rticonnextdds-cmake-utils.git
        GIT_TAG ${RTICONNEXT_CMAKE_UTILS_GIT_TAG}
    )
    FetchContent_MakeAvailable(rticonnextdds_cmake_utils)

    # CONNEXTDDS_DIR (or $NDDSHOME) must point to the Connext 7.7.0 install; the
    # module itself resolves it, so it is read as a plain variable, not HINTS.
    list(APPEND CMAKE_MODULE_PATH "${CONNEXTDDS_DIR}/resource/cmake")
    find_package(RTIConnextDDS 7.7.0 REQUIRED COMPONENTS core)
    include(ConnextDdsCodegen)
    connextdds_rtiddsgen_run(
        IDL_FILE "${CMAKE_CURRENT_SOURCE_DIR}/VehicleState.idl"
        OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated"
        LANG C++11
    )

    add_executable(rti_demo_ui_connext
        connext.cpp
        ${VehicleState_CXX11_SOURCES}
    )
    target_include_directories(rti_demo_ui_connext PRIVATE
        ${VehicleState_CXX11_INCLUDE_DIRS}
        "${CMAKE_CURRENT_BINARY_DIR}/generated"
    )
    target_link_libraries(rti_demo_ui_connext PRIVATE
        rti_demo_ui::core
        RTIConnextDDS::cpp2_api
    )
endif()
