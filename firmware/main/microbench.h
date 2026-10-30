/* Diagnostic single-core kernels: controlled scratch data, never model weights. */
#include "esp_memory_utils.h"
#define MB_SMALL 24576u
#define MB_LARGE 1048576u
static volatile uint32_t mb_sink;
static __attribute__((noinline)) uint32_t mb_read(const uint32_t *p,size_t bytes) {
    const volatile uint32_t *v=p;uint32_t sum=0;
    for(size_t i=0;i<bytes/4;i++)sum+=v[i];
    return sum;
}
static __attribute__((noinline)) uint32_t mb_unpack(const uint8_t *p,size_t bytes) {
    uint32_t sum=0;
    for(size_t i=0;i<bytes;i++){int a=p[i]&15,b=p[i]>>4;sum+=(uint32_t)((a<8?a:a-16)+(b<8?b:b-16));}
    return sum;
}
static __attribute__((noinline)) float mb_matrix(const uint8_t *p,const float *x) {
    float check=0;
    for(int row=0;row<64;row+=4){float a=0,b=0,c=0,d=0;
        const uint8_t *q=p+(size_t)row*384;
        for(int j=0;j<768;j++){int shift=(j&1)*4;
            int u=(q[j/2]>>shift)&15,v=(q[384+j/2]>>shift)&15,w=(q[768+j/2]>>shift)&15,z=(q[1152+j/2]>>shift)&15;
            float f=x[j];a+=(float)(u<8?u:u-16)*f;b+=(float)(v<8?v:v-16)*f;
            c+=(float)(w<8?w:w-16)*f;d+=(float)(z<8?z:z-16)*f;
        }check+=a+b+c+d;
    }return check;
}
static esp_err_t microbench(httpd_req_t *r) {
    if(!allowed(r)||!idle(r))return ESP_OK;
    if(r->content_len!=1)return error(r,"400 Bad Request","One run digit required");
    char digit;if(receive(r,&digit,1))return ESP_FAIL;
    if(digit<'0'||digit>'5')return error(r,"400 Bad Request","Run must be0..5");
    if(!dispatcher_maintenance_begin())return error(r,"409 Conflict","Dispatcher busy");
    uint8_t *ram=heap_caps_malloc(MB_SMALL,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    uint8_t *ps=heap_caps_malloc(MB_LARGE,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    float *x=heap_caps_malloc(768*4,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    if(!ram||!ps||!x){free(ram);free(ps);free(x);dispatcher_maintenance_end();return error(r,"503 Service Unavailable","Scratch allocation failed");}
    for(size_t i=0;i<MB_LARGE;i++)ps[i]=(uint8_t)(i*37u+11u);
    memcpy(ram,ps,MB_SMALL);for(int i=0;i<768;i++)x[i]=(float)((i%17)-8)/16;
    uint32_t scan_small=mb_read((uint32_t*)ram,MB_SMALL),scan_large=mb_read((uint32_t*)ps,MB_LARGE),unpack=mb_unpack(ram,MB_SMALL);
    float matrix=mb_matrix(ram,x);int valid=esp_ptr_internal(ram)&&esp_ptr_internal(x)&&esp_ptr_external_ram(ps);
    cJSON *root=cJSON_CreateObject(),*rows=cJSON_AddArrayToObject(root,"measurements");
    const char *names[]={"read_internal_small","read_psram_small","read_psram_large","unpack_internal","unpack_psram_stream","matrix_internal","matrix_psram_small","matrix_psram_stream"};
    for(int order=0;order<8;order++){
        int mode=(order+(digit-'0'))%8;uint64_t elapsed=0;unsigned calls=mode==2?8:42;uint32_t isum=0;float fsum=0;
        /* Each timed chunk is bounded; yields are outside the measured spans. */
        for(unsigned k=0;k<calls;k++){
            const uint8_t *q=mode==0||mode==3||mode==5?ram:ps;
            if(mode==4||mode==7)q=ps+(size_t)(k%42)*MB_SMALL;
            int64_t start=esp_timer_get_time();
            if(mode<=2){uint32_t v=mb_read((const uint32_t*)q,mode==2?MB_LARGE:MB_SMALL);elapsed+=esp_timer_get_time()-start;isum+=v;valid&=v==(mode==2?scan_large:scan_small);}
            else if(mode<=4){uint32_t v=mb_unpack(q,MB_SMALL);elapsed+=esp_timer_get_time()-start;isum+=v;valid&=v==unpack;}
            else {float v=mb_matrix(q,x);elapsed+=esp_timer_get_time()-start;fsum+=v;valid&=v==matrix;}
            vTaskDelay(1);
        }
        mb_sink^=isum+(uint32_t)(int32_t)fsum;
        cJSON *item=cJSON_CreateObject();cJSON_AddStringToObject(item,"mode",names[mode]);cJSON_AddNumberToObject(item,"timed_us",elapsed);
        cJSON_AddNumberToObject(item,"calls",calls);cJSON_AddNumberToObject(item,"logical_bytes",(double)calls*(mode==2?MB_LARGE:MB_SMALL));
        cJSON_AddNumberToObject(item,"uint_checksum",isum);cJSON_AddNumberToObject(item,"float_checksum",fsum);cJSON_AddItemToArray(rows,item);
    }
    cJSON_AddBoolToObject(root,"valid",valid);cJSON_AddNumberToObject(root,"run",digit-'0');cJSON_AddNumberToObject(root,"core",xPortGetCoreID());
    cJSON_AddNumberToObject(root,"matrix_reference",matrix);cJSON_AddNumberToObject(root,"scan_small_reference",scan_small);cJSON_AddNumberToObject(root,"scan_large_reference",scan_large);cJSON_AddNumberToObject(root,"unpack_reference",unpack);
    free(ram);free(ps);free(x);dispatcher_maintenance_end();
    char *body=cJSON_PrintUnformatted(root);cJSON_Delete(root);httpd_resp_set_type(r,"application/json");esp_err_t result=httpd_resp_sendstr(r,body);free(body);return result;
}
