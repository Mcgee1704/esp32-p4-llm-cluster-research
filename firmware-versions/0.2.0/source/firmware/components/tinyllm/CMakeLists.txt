idf_component_register(SRCS "tinyllm.c" "cluster_rpc.c" INCLUDE_DIRS "include" REQUIRES heap freertos)
target_compile_options(${COMPONENT_LIB} PRIVATE -ffp-contract=off)
