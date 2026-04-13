cmake_minimum_required(VERSION 3.20)
project(urban_rail_cg_cpp LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(URBAN_RAIL_CG_SOURCES
    src/main.cpp
)

add_executable(urban_rail_cg
    ${URBAN_RAIL_CG_SOURCES}
)

add_executable(urban_rail_cg_v3
    ${URBAN_RAIL_CG_SOURCES}
)

foreach(target_name IN ITEMS urban_rail_cg urban_rail_cg_v3)
    if(MSVC)
        target_compile_options(${target_name} PRIVATE /W4 /EHsc)
    else()
        target_compile_options(${target_name} PRIVATE -Wall -Wextra -Wpedantic)
    endif()
endforeach()
