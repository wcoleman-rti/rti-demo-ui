cmake_minimum_required(VERSION 3.16)

add_executable(rti_demo_ui_component_tests component_tests.cpp)
target_link_libraries(rti_demo_ui_component_tests PRIVATE rti_demo_ui::core)
target_compile_definitions(rti_demo_ui_component_tests PRIVATE
    SOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
add_test(NAME component_tests COMMAND rti_demo_ui_component_tests)

add_executable(rti_demo_ui_http_tests http_tests.cpp)
target_link_libraries(rti_demo_ui_http_tests PRIVATE rti_demo_ui::core)
target_compile_definitions(rti_demo_ui_http_tests PRIVATE
    SOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
add_test(NAME http_tests COMMAND rti_demo_ui_http_tests)

add_executable(rti_demo_ui_static_root_tests static_root_tests.cpp)
target_link_libraries(rti_demo_ui_static_root_tests
    PRIVATE rti_demo_ui::core nlohmann_json::nlohmann_json
)
target_compile_definitions(rti_demo_ui_static_root_tests PRIVATE
    SOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
add_test(NAME static_root_tests COMMAND rti_demo_ui_static_root_tests)

add_executable(rti_demo_ui_lifecycle_tests lifecycle_tests.cpp)
target_link_libraries(rti_demo_ui_lifecycle_tests PRIVATE rti_demo_ui::core)
add_test(NAME lifecycle_tests COMMAND rti_demo_ui_lifecycle_tests)
set_tests_properties(lifecycle_tests PROPERTIES TIMEOUT 30)

add_executable(rti_demo_ui_sse_tests sse_tests.cpp)
target_link_libraries(rti_demo_ui_sse_tests PRIVATE rti_demo_ui::core)
add_test(NAME sse_tests COMMAND rti_demo_ui_sse_tests)
set_tests_properties(sse_tests PROPERTIES TIMEOUT 10)

add_executable(rti_demo_ui_presentation_contract_tests
    presentation_contract_tests.cpp
)
target_link_libraries(rti_demo_ui_presentation_contract_tests
    PRIVATE rti_demo_ui::core
)
target_compile_definitions(rti_demo_ui_presentation_contract_tests PRIVATE
    SOURCE_ROOT="${CMAKE_CURRENT_SOURCE_DIR}/../.."
)
add_test(
    NAME presentation_contract_tests
    COMMAND rti_demo_ui_presentation_contract_tests
)
