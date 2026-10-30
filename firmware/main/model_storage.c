#include "model_storage.h"
#include "model_envelope.h"
#include "esp_heap_caps.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "miniz.h"
#include <stdlib.h>
#include <string.h>

int model_storage_header(const uint8_t h[128],size_t stored,size_t *expanded) {
    *expanded=ts_storage_expanded(h,stored);return *expanded!=0;
}

void *model_storage_read(const esp_partition_t *p,const uint8_t h[128],size_t stored,const char **error) {
    size_t expanded;if(stored>p->size||!model_storage_header(h,stored,&expanded)){*error="Invalid model envelope";return NULL;}
    uint8_t *out=heap_caps_malloc(expanded,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!out){*error="Insufficient PSRAM for expanded model";return NULL;}
    mbedtls_sha256_context hash;mbedtls_sha256_init(&hash);mbedtls_sha256_starts(&hash,0);mbedtls_sha256_update(&hash,h,48);
    uint8_t digest[32];uint8_t *input=NULL;tinfl_decompressor *d=NULL;
    if(memcmp(h,"P4ZL0001",8)) {
        if(esp_partition_read(p,0,out,expanded)!=ESP_OK){*error="Model flash read failed";goto fail;}
        mbedtls_sha256_update(&hash,out+128,expanded-128);
    } else {
        input=malloc(4096);d=calloc(1,sizeof *d);
        if(!input||!d){*error="Decompressor allocation failed";goto fail;}
        tinfl_init(d);size_t read_at=128,filled=0,used=0,in_total=0,out_total=0;
        int64_t pause=esp_timer_get_time()+10000;tinfl_status status=TINFL_STATUS_NEEDS_MORE_INPUT;
        while(status!=TINFL_STATUS_DONE) {
            if(used==filled&&read_at<stored) {
                filled=stored-read_at;if(filled>4096)filled=4096;used=0;
                if(esp_partition_read(p,read_at,input,filled)!=ESP_OK){*error="Compressed flash read failed";goto fail;}
                mbedtls_sha256_update(&hash,input,filled);read_at+=filled;
            }
            size_t in=filled-used,n=expanded-out_total;if(n>65536)n=65536;
            unsigned flags=TINFL_FLAG_PARSE_ZLIB_HEADER|TINFL_FLAG_USING_NON_WRAPPING_OUTPUT_BUF;
            if(read_at<stored)flags|=TINFL_FLAG_HAS_MORE_INPUT;
            status=tinfl_decompress(d,input+used,&in,out,out+out_total,&n,flags);
            used+=in;in_total+=in;out_total+=n;
            if(status<TINFL_STATUS_DONE||(!in&&!n&&status!=TINFL_STATUS_DONE)||out_total>expanded){*error="Invalid or truncated zlib model";goto fail;}
            if(esp_timer_get_time()>=pause){vTaskDelay(1);pause=esp_timer_get_time()+10000;}
        }
        if(in_total!=stored-128||out_total!=expanded||memcmp(out,"P4QS0001",8)){*error="Expanded model length/format mismatch";goto fail;}
    }
    mbedtls_sha256_finish(&hash,digest);
    if(memcmp(digest,h+48,32)){*error="Stored model SHA256 mismatch";goto fail;}
    if(!memcmp(h,"P4ZL0001",8)) {
        mbedtls_sha256_starts(&hash,0);mbedtls_sha256_update(&hash,out,expanded);mbedtls_sha256_finish(&hash,digest);
        if(memcmp(digest,h+84,32)){*error="Expanded model SHA256 mismatch";goto fail;}
        size_t inner;if(!model_storage_header(out,expanded,&inner)||inner!=expanded){*error="Invalid expanded envelope";goto fail;}
        mbedtls_sha256_starts(&hash,0);mbedtls_sha256_update(&hash,out,48);mbedtls_sha256_update(&hash,out+128,expanded-128);mbedtls_sha256_finish(&hash,digest);
        if(memcmp(digest,out+48,32)){*error="Expanded artifact SHA256 mismatch";goto fail;}
    }
    free(input);free(d);mbedtls_sha256_free(&hash);return out;
fail:
    free(input);free(d);free(out);mbedtls_sha256_free(&hash);return NULL;
}
