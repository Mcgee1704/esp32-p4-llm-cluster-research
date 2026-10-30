idf_component_register(SRCS "tinyllm.c" "model_envelope.c" "gpt2_tokenizer.c" "cluster_rpc.c" INCLUDE_DIRS "include" REQUIRES heap freertos esp_timer esp_hw_support)
target_compile_options(${COMPONENT_LIB} PRIVATE -ffp-contract=off)
