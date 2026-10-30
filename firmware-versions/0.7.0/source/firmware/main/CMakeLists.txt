idf_component_register(SRCS "main.c" "model_storage.c" "lan.c" "service.c" "dispatcher.c"
    INCLUDE_DIRS "."
    REQUIRES tinyllm dispatch_queue esp_eth esp_netif esp_http_server esp_http_client app_update
             esp_partition nvs_flash esp_psram esp_timer json mbedtls esp_driver_gpio
    EMBED_FILES "index.html" "cluster.html")
