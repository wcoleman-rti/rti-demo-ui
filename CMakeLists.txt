cmake_minimum_required(VERSION 3.16)
project(rti_demo_ui LANGUAGES CXX)

include(CTest)
set(RTI_DEMO_TOP_LEVEL_BUILD ON)
add_subdirectory(cpp)
