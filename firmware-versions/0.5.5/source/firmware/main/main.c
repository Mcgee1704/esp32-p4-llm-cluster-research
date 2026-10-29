#include "app.h"
#include "esp_log.h"
#include "esp_partition.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "nvs_flash.h"
#include "mbedtls/sha256.h"
#include <string.h>
#include <stdlib.h>
ts_state *model;
rpc_state *worker;
const char *model_error="No model uploaded";
static void *model_blob;
size_t model_load_free_psram,model_load_largest_psram,model_load_requested;
void model_load(void) {
    rpc_close(worker);worker=NULL;ts_close(model);model=NULL;free(model_blob);model_blob=NULL;
    const esp_partition_t *p=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x40,"model");
    uint8_t header[128];
    if(!p||esp_partition_read(p,0,header,sizeof header)!=ESP_OK||
       (memcmp(header,"P4LM0001",8)&&memcmp(header,"P4GN0001",8))) {
        model_error="No valid model header. Upload a .p4lm or .p4gn file over LAN.";return;
    }
    uint32_t w,t;memcpy(&w,header+36,4);memcpy(&t,header+40,4);
    if(w>p->size-128||t>p->size-128-w) {model_error="Model length invalid";return;}
    size_t bytes=128+(size_t)w+t;
    model_load_requested=bytes;
    model_load_free_psram=heap_caps_get_free_size(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    model_load_largest_psram=heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    model_blob=heap_caps_malloc(bytes,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!model_blob){model_error="Insufficient PSRAM for model";return;}
    if(esp_partition_read(p,0,model_blob,bytes)!=ESP_OK){model_error="Model flash read failed";goto fail;}
    uint8_t sha[32];mbedtls_sha256_context hash;mbedtls_sha256_init(&hash);
    mbedtls_sha256_starts(&hash,0);mbedtls_sha256_update(&hash,header,48);
    mbedtls_sha256_update(&hash,(uint8_t*)model_blob+128,bytes-128);
    mbedtls_sha256_finish(&hash,sha);mbedtls_sha256_free(&hash);
    if(memcmp(sha,header+48,32)) {
        model_error="Model SHA256 mismatch";goto fail;
    }
    model=ts_open(model_blob,bytes);
    if(!model){model_error="Model format or runtime memory invalid";goto fail;}
    worker=rpc_open(model);if(!worker){model_error="Worker allocation failed";goto fail;}
    model_error="";
    ESP_LOGI("model","Ready: %u bytes, %u layers, free PSRAM %u",(unsigned)bytes,
        (unsigned)ts_config_get(model)->layers,(unsigned)heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    return;
fail:
    ts_close(model);model=NULL;free(model_blob);model_blob=NULL;
}
void app_main(void) {
    ESP_ERROR_CHECK(nvs_flash_init());
    /* Keep LAN recovery available even when no/invalid model is installed. */
    if(esp_psram_is_initialized())model_load();else model_error="PSRAM initialization failed";
    lan_start();service_start();
}
