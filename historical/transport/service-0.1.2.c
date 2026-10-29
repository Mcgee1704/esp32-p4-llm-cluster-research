#include "app.h"
#include "esp_http_server.h"
#include "esp_http_client.h"
#include "esp_ota_ops.h"
#include "esp_app_desc.h"
#include "esp_partition.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_system.h"
#include "esp_heap_caps.h"
#include "esp_psram.h"
#include "esp_log.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "mbedtls/sha256.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"
#include "cJSON.h"
#include "sdkconfig.h"
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include <stdio.h>
#include <math.h>

/* A single HTTP task owns inference, model replacement and worker leases.
 * No inference and flash write can run concurrently. Every session is bounded. */
static int64_t lease_until;
static const char *key=CONFIG_CLUSTER_KEY;
typedef struct {
    int64_t master_compute,stream,rpc_total,open,write,wait,read,worker_compute;
    unsigned calls,connections,worker_reports;
} timing_profile;
static esp_err_t rpc_event(esp_http_client_event_t *event) {
    timing_profile *p=event->user_data;
    if(event->event_id==HTTP_EVENT_ON_CONNECTED)p->connections++;
    if(event->event_id==HTTP_EVENT_ON_HEADER&&!strcasecmp(event->header_key,"X-RPC-Compute-Us")) {
        char *end;long long value=strtoll(event->header_value,&end,10);
        if(end!=event->header_value&&!*end&&value>=0&&value<=120000000) {
            p->worker_compute+=value;p->worker_reports++;
        }
    }
    return ESP_OK;
}
static void profile_reply(cJSON *done,const timing_profile *p) {
    cJSON *j=cJSON_AddObjectToObject(done,"profile");
    cJSON_AddNumberToObject(j,"master_compute_ms",p->master_compute/1000.0);
    cJSON_AddNumberToObject(j,"stream_ms",p->stream/1000.0);
    cJSON_AddNumberToObject(j,"rpc_total_ms",p->rpc_total/1000.0);
    cJSON_AddNumberToObject(j,"rpc_open_ms",p->open/1000.0);
    cJSON_AddNumberToObject(j,"rpc_write_ms",p->write/1000.0);
    cJSON_AddNumberToObject(j,"rpc_wait_headers_ms",p->wait/1000.0);
    cJSON_AddNumberToObject(j,"rpc_read_ms",p->read/1000.0);
    cJSON_AddNumberToObject(j,"worker_compute_ms",p->worker_compute/1000.0);
    cJSON_AddNumberToObject(j,"rpc_calls",p->calls);
    cJSON_AddNumberToObject(j,"connections",p->connections);
    cJSON_AddNumberToObject(j,"worker_reports",p->worker_reports);
}
extern const unsigned char index_start[] asm("_binary_index_html_start");
extern const unsigned char index_end[] asm("_binary_index_html_end");
static esp_err_t error(httpd_req_t *r,const char *status,const char *why) {
    httpd_resp_set_status(r,status);httpd_resp_set_type(r,"text/plain; charset=utf-8");
    return httpd_resp_send(r,why,HTTPD_RESP_USE_STRLEN);
}
static int allowed(httpd_req_t *r) {
    char given[129];size_t len=strlen(key);
    if(len<24||len>128||httpd_req_get_hdr_value_str(r,"X-Cluster-Key",given,sizeof given)!=ESP_OK||strlen(given)!=len) {
        error(r,"401 Unauthorized","LAN key missing or invalid");return 0;
    }
    unsigned diff=0;for(size_t i=0;i<len;i++)diff|=(unsigned char)key[i]^(unsigned char)given[i];
    if(diff){error(r,"401 Unauthorized","LAN key invalid");return 0;}return 1;
}
static int receive(httpd_req_t *r,void *data,size_t count) {
    char *p=data;int timeouts=0;
    while(count) {
        int n=httpd_req_recv(r,p,count);
        if(n==HTTPD_SOCK_ERR_TIMEOUT&&timeouts++<3)continue;
        if(n<=0)return -1;
        p+=n;count-=n;
    }
    return 0;
}
static void expire(void) {
    if(worker&&rpc_active(worker)&&esp_timer_get_time()>lease_until)rpc_expire(worker);
}
static int idle(httpd_req_t *r) {
    expire();if(rpc_active(worker)){error(r,"409 Conflict","Worker session active");return 0;}return 1;
}
static esp_err_t json_reply(httpd_req_t *r,cJSON *j) {
    char *text=cJSON_PrintUnformatted(j);cJSON_Delete(j);
    if(!text)return error(r,"500 Internal Server Error","Out of memory");
    httpd_resp_set_type(r,"application/json");esp_err_t e=httpd_resp_send(r,text,HTTPD_RESP_USE_STRLEN);free(text);return e;
}
static esp_err_t index_page(httpd_req_t *r) {
    httpd_resp_set_type(r,"text/html; charset=utf-8");
    httpd_resp_set_hdr(r,"Cache-Control","no-store");
    httpd_resp_set_hdr(r,"X-Content-Type-Options","nosniff");
    return httpd_resp_send(r,(const char*)index_start,index_end-index_start);
}
static esp_err_t status(httpd_req_t *r) {
    if(!allowed(r))return ESP_OK;
    expire();
    cJSON *j=cJSON_CreateObject();
    cJSON_AddStringToObject(j,"firmware",esp_app_get_description()->version);
    cJSON_AddBoolToObject(j,"model_ready",model!=NULL);
    cJSON_AddStringToObject(j,"model_error",model_error);
    cJSON_AddBoolToObject(j,"worker_busy",rpc_active(worker));
    cJSON_AddNumberToObject(j,"free_psram",heap_caps_get_free_size(MALLOC_CAP_SPIRAM));
    cJSON_AddStringToObject(j,"storage","internal flash; SD not required for inference");
    if(model){const ts_config *c=ts_config_get(model);cJSON_AddNumberToObject(j,"layers",c->layers);
        cJSON_AddNumberToObject(j,"context",c->context);cJSON_AddNumberToObject(j,"dim",c->dim);
        char sha[65];for(int i=0;i<32;i++)sprintf(sha+i*2,"%02x",ts_model_id(model)[i]);
        cJSON_AddStringToObject(j,"model_id",sha);}
    esp_ota_img_states_t state;
    bool pending=esp_ota_get_state_partition(esp_ota_get_running_partition(),&state)==ESP_OK&&state==ESP_OTA_IMG_PENDING_VERIFY;
    cJSON_AddBoolToObject(j,"ota_pending",pending);
    return json_reply(r,j);
}
static esp_err_t rpc_handler(httpd_req_t *r) {
    if(!allowed(r))return ESP_OK;
    /* RPC frames are small and sequential: do not wait for delayed ACKs
     * between the separately written HTTP headers and response body. */
    int nodelay=1;
    if(setsockopt(httpd_req_to_sockfd(r),IPPROTO_TCP,TCP_NODELAY,&nodelay,sizeof nodelay)<0)
        return error(r,"500 Internal Server Error","Could not configure RPC socket");
    expire();
    if(!model)return error(r,"503 Service Unavailable",model_error);
    if(r->content_len<64||r->content_len>RPC_MAX_FRAME)return error(r,"400 Bad Request","RPC length invalid");
    uint8_t *in=malloc(r->content_len),*out=malloc(RPC_MAX_FRAME);
    if(!in||!out){free(in);free(out);return error(r,"500 Internal Server Error","Out of memory");}
    int n=-1;int64_t compute=0;
    if(!receive(r,in,r->content_len)) {
        int64_t start=esp_timer_get_time();
        n=rpc_dispatch(worker,in,r->content_len,out,RPC_MAX_FRAME);
        compute=esp_timer_get_time()-start;
    }
    free(in);
    if(n<0){free(out);return error(r,"409 Conflict","RPC model, session or position mismatch");}
    lease_until=esp_timer_get_time()+120000000;
    char timing[24];snprintf(timing,sizeof timing,"%lld",(long long)compute);
    httpd_resp_set_hdr(r,"X-RPC-Compute-Us",timing);
    httpd_resp_set_type(r,"application/octet-stream");esp_err_t e=httpd_resp_send(r,(char*)out,n);free(out);return e;
}
static int remote_step(esp_http_client_handle_t client,rpc_header *h,float *x,timing_profile *p) {
    int64_t start=esp_timer_get_time(),phase=start;p->calls++;
    uint8_t frame[RPC_MAX_FRAME];memcpy(frame,h,64);if(h->bytes)memcpy(frame+64,x,h->bytes);
    int length=(int)(64+h->bytes);
    if(esp_http_client_open(client,length)!=ESP_OK)return -1;
    /* open() writes HTTP headers; flush them immediately before the body. */
    int nodelay=1;
    if(setsockopt(esp_http_client_get_socket(client),IPPROTO_TCP,TCP_NODELAY,&nodelay,sizeof nodelay)<0)goto bad;
    p->open+=esp_timer_get_time()-phase;phase=esp_timer_get_time();
    int offset=0;
    while(offset<length){int n=esp_http_client_write(client,(char*)frame+offset,length-offset);if(n<=0)goto bad;offset+=n;}
    p->write+=esp_timer_get_time()-phase;phase=esp_timer_get_time();
    if(esp_http_client_fetch_headers(client)!=length||esp_http_client_get_status_code(client)!=200)goto bad;
    p->wait+=esp_timer_get_time()-phase;phase=esp_timer_get_time();
    offset=0;while(offset<length){int n=esp_http_client_read(client,(char*)frame+offset,length-offset);if(n<=0)goto bad;offset+=n;}
    if(memcmp(frame,h,64))goto bad;
    if(h->bytes)memcpy(x,frame+64,h->bytes);
    p->read+=esp_timer_get_time()-phase;
    esp_http_client_close(client);p->rpc_total+=esp_timer_get_time()-start;return 0;
bad:esp_http_client_close(client);p->rpc_total+=esp_timer_get_time()-start;return -1;
}
static esp_err_t line(httpd_req_t *r,cJSON *j) {
    char *s=cJSON_PrintUnformatted(j);cJSON_Delete(j);if(!s)return ESP_ERR_NO_MEM;
    esp_err_t e=httpd_resp_send_chunk(r,s,strlen(s));free(s);
    if(e==ESP_OK)e=httpd_resp_send_chunk(r,"\n",1);
    return e;
}
static esp_err_t generate(httpd_req_t *r) {
    if(!allowed(r)||!idle(r))return ESP_OK;
    if(!model)return error(r,"503 Service Unavailable",model_error);
    if(!r->content_len||r->content_len>2048)return error(r,"400 Bad Request","Request too long");
    char body[2049];if(receive(r,body,r->content_len))return ESP_FAIL;body[r->content_len]=0;
    int64_t start=esp_timer_get_time();
    timing_profile profile={0};
    cJSON *j=cJSON_Parse(body);if(!j)return error(r,"400 Bad Request","Invalid JSON");
    cJSON *prompt=cJSON_GetObjectItemCaseSensitive(j,"prompt"),*peer=cJSON_GetObjectItemCaseSensitive(j,"peer"),*limit=cJSON_GetObjectItemCaseSensitive(j,"tokens");
    if(!cJSON_IsString(prompt)||strlen(prompt->valuestring)>1024||
       !cJSON_IsNumber(limit)||limit->valuedouble<1||limit->valuedouble>128||limit->valuedouble!=limit->valueint||
       (peer&&!cJSON_IsString(peer))) {cJSON_Delete(j);return error(r,"400 Bad Request","Invalid prompt, peer or token limit");}
    const ts_config *c=ts_config_get(model);int *tokens=malloc((c->context+1026)*sizeof(int));
    if(!tokens){cJSON_Delete(j);return error(r,"500 Internal Server Error","Out of memory");}
    int count=ts_encode(model,prompt->valuestring,tokens,(int)c->context+1026),steps=limit->valueint;
    if(count<1||count+steps-1>(int)c->context){free(tokens);cJSON_Delete(j);return error(r,"400 Bad Request","Prompt plus output exceeds model context");}
    esp_http_client_handle_t client=NULL;rpc_header h={.magic=RPC_MAGIC,.command=1,.session=esp_random()|1u,.split=c->layers/2,.dim=c->dim};
    memcpy(h.model,ts_model_id(model),32);
    if(peer&&*peer->valuestring) {
        struct in_addr ip;
        if(inet_pton(AF_INET,peer->valuestring,&ip)!=1||!ip.s_addr||ip.s_addr==INADDR_BROADCAST||ip.s_addr==lan_ip4) {
            free(tokens);cJSON_Delete(j);return error(r,"400 Bad Request","Peer must be a LAN IPv4 address");}
        /* Refuse non-private/link-local destinations: inference data stays in the LAN. */
        uint32_t a=ntohl(ip.s_addr);
        if(!((a>>24)==10||(a>>20)==0xac1||(a>>16)==0xc0a8||(a>>16)==0xa9fe)) {
            free(tokens);cJSON_Delete(j);return error(r,"400 Bad Request","Only private LAN peers allowed");}
        char url[80];snprintf(url,sizeof url,"http://%s/api/rpc",peer->valuestring);
        esp_http_client_config_t cfg={.url=url,.method=HTTP_METHOD_POST,.timeout_ms=120000,.disable_auto_redirect=true,
            .event_handler=rpc_event,.user_data=&profile};
        client=esp_http_client_init(&cfg);
        if(!client){free(tokens);cJSON_Delete(j);return error(r,"500 Internal Server Error","Client allocation failed");}
        esp_http_client_set_header(client,"X-Cluster-Key",key);
        esp_http_client_set_header(client,"Content-Type","application/octet-stream");
        if(remote_step(client,&h,NULL,&profile)){esp_http_client_cleanup(client);free(tokens);cJSON_Delete(j);return error(r,"503 Service Unavailable","Worker unavailable, busy or different model");}
    }
    cJSON_Delete(j);ts_reset(model);
    httpd_resp_set_type(r,"application/x-ndjson");httpd_resp_set_hdr(r,"Cache-Control","no-store");
    int token=tokens[0],produced=0;int64_t first=0;const char *failure=NULL;
    for(int pos=0;pos<count+steps-1;pos++) {
        int64_t phase=esp_timer_get_time();
        if(ts_embed(model,token)||ts_layers(model,0,client?(int)h.split:(int)c->layers,pos)){failure="Inference failed";break;}
        profile.master_compute+=esp_timer_get_time()-phase;
        if(client){h.command=2;h.position=pos;h.bytes=c->dim*4;
            if(remote_step(client,&h,ts_x(model),&profile)){failure="Worker connection failed; request aborted";break;}}
        int next;
        if(pos<count-1)next=tokens[pos+1];
        else {
            phase=esp_timer_get_time();ts_finish(model);next=ts_argmax(model);
            profile.master_compute+=esp_timer_get_time()-phase;
            if(!first)first=esp_timer_get_time();
            if(next==1||next==2)break;
            const char *piece=ts_decode(model,token,next);size_t length=strlen(piece);char hex[1025];
            for(size_t i=0;i<length;i++)sprintf(hex+i*2,"%02x",(unsigned char)piece[i]);
            hex[length*2]=0;
            cJSON *item=cJSON_CreateObject();cJSON_AddStringToObject(item,"bytes_hex",hex);
            cJSON_AddNumberToObject(item,"token",next);
            phase=esp_timer_get_time();esp_err_t sent=line(r,item);
            profile.stream+=esp_timer_get_time()-phase;
            if(sent!=ESP_OK){failure="Client disconnected";break;}produced++;
        }
        token=next;
    }
    if(client){h.command=3;h.bytes=0;(void)remote_step(client,&h,NULL,&profile);esp_http_client_cleanup(client);}
    free(tokens);
    cJSON *done=cJSON_CreateObject();cJSON_AddBoolToObject(done,"done",true);
    cJSON_AddNumberToObject(done,"output_tokens",produced);cJSON_AddNumberToObject(done,"elapsed_ms",(esp_timer_get_time()-start)/1000.0);
    cJSON_AddNumberToObject(done,"ttft_ms",first?(first-start)/1000.0:0);cJSON_AddNumberToObject(done,"boards",client?2:1);
    profile_reply(done,&profile);
    if(failure)cJSON_AddStringToObject(done,"error",failure);
    line(r,done);return httpd_resp_send_chunk(r,NULL,0);
}
static void restart_task(void *arg) {(void)arg;vTaskDelay(pdMS_TO_TICKS(2000));esp_restart();}
static esp_err_t firmware_upload(httpd_req_t *r) {
    if(!allowed(r)||!idle(r))return ESP_OK;
    const esp_partition_t *target=esp_ota_get_next_update_partition(NULL);
    if(!target||r->content_len<1024||r->content_len>target->size)return error(r,"400 Bad Request","Invalid firmware length");
    esp_ota_handle_t ota;esp_err_t e=esp_ota_begin(target,r->content_len,&ota);
    if(e!=ESP_OK)return error(r,"409 Conflict","OTA unavailable; previous update may still await boot verification");
    char buffer[4096];size_t left=r->content_len;
    while(left){size_t n=left<sizeof buffer?left:sizeof buffer;
        if(receive(r,buffer,n)||esp_ota_write(ota,buffer,n)!=ESP_OK){esp_ota_abort(ota);return error(r,"400 Bad Request","Firmware transfer aborted; active slot unchanged");}left-=n;}
    if(esp_ota_end(ota)!=ESP_OK)return error(r,"400 Bad Request","Firmware validation failed; active slot unchanged");
    if(esp_ota_set_boot_partition(target)!=ESP_OK)return error(r,"500 Internal Server Error","Could not select update slot");
    httpd_resp_sendstr(r,"Firmware accepted. Rebooting; LAN boot check follows.");
    xTaskCreate(restart_task,"reboot",2048,NULL,5,NULL);return ESP_OK;
}
static esp_err_t model_upload(httpd_req_t *r) {
    if(!allowed(r)||!idle(r))return ESP_OK;
    const esp_partition_t *p=esp_partition_find_first(ESP_PARTITION_TYPE_DATA,0x40,"model");
    if(!p||r->content_len<128||r->content_len>p->size)return error(r,"400 Bad Request","Invalid model length");
    uint8_t header[128];if(receive(r,header,sizeof header))return ESP_FAIL;
    uint32_t w,t;memcpy(&w,header+36,4);memcpy(&t,header+40,4);
    if(memcmp(header,"P4LM0001",8)||w>r->content_len-128||t!=r->content_len-128-w)return error(r,"400 Bad Request","Wrong model format");
    /* Invalidate on flash first; old in-RAM model is replaced only after upload.
     * Header is written last: power loss cannot mark a partial file as complete. */
    size_t erase=(r->content_len+4095)&~(size_t)4095;
    if(esp_partition_erase_range(p,0,erase)!=ESP_OK)return error(r,"500 Internal Server Error","Model erase failed");
    mbedtls_sha256_context hash;mbedtls_sha256_init(&hash);mbedtls_sha256_starts(&hash,0);mbedtls_sha256_update(&hash,header,48);
    uint8_t data[4096],digest[32];size_t offset=128;
    while(offset<r->content_len){size_t n=r->content_len-offset;if(n>sizeof data)n=sizeof data;
        if(receive(r,data,n)||esp_partition_write(p,offset,data,n)!=ESP_OK){mbedtls_sha256_free(&hash);return error(r,"400 Bad Request","Model interrupted. Re-upload before next reboot.");}
        mbedtls_sha256_update(&hash,data,n);offset+=n;}
    mbedtls_sha256_finish(&hash,digest);mbedtls_sha256_free(&hash);
    if(memcmp(digest,header+48,32))return error(r,"400 Bad Request","Model hash mismatch; re-upload required");
    if(esp_partition_write(p,0,header,sizeof header)!=ESP_OK)return error(r,"500 Internal Server Error","Model commit failed");
    model_load();if(!model)return error(r,"400 Bad Request",model_error);
    return httpd_resp_sendstr(r,"Model loaded and verified.");
}
static void boot_check(void *arg) {
    (void)arg;esp_ota_img_states_t state;
    bool pending=esp_ota_get_state_partition(esp_ota_get_running_partition(),&state)==ESP_OK&&state==ESP_OTA_IMG_PENDING_VERIFY;
    if(pending) {
        for(int n=0;n<120&&!lan_ready;n++)vTaskDelay(pdMS_TO_TICKS(1000));
        if(lan_ready&&esp_psram_is_initialized()) {
            vTaskDelay(pdMS_TO_TICKS(10000));
            if(lan_ready)ESP_ERROR_CHECK(esp_ota_mark_app_valid_cancel_rollback());
            else esp_ota_mark_app_invalid_rollback_and_reboot();
        } else esp_ota_mark_app_invalid_rollback_and_reboot();
    }
    vTaskDelete(NULL);
}
void service_start(void) {
    httpd_config_t cfg=HTTPD_DEFAULT_CONFIG();cfg.stack_size=16384;cfg.recv_wait_timeout=10;cfg.send_wait_timeout=30;cfg.max_uri_handlers=8;
    httpd_handle_t server;ESP_ERROR_CHECK(httpd_start(&server,&cfg));
    const httpd_uri_t routes[]={
        {.uri="/",.method=HTTP_GET,.handler=index_page},
        {.uri="/api/status",.method=HTTP_GET,.handler=status},
        {.uri="/api/generate",.method=HTTP_POST,.handler=generate},
        {.uri="/api/rpc",.method=HTTP_POST,.handler=rpc_handler},
        {.uri="/api/model",.method=HTTP_POST,.handler=model_upload},
        {.uri="/api/firmware",.method=HTTP_POST,.handler=firmware_upload}};
    for(size_t i=0;i<sizeof routes/sizeof routes[0];i++)ESP_ERROR_CHECK(httpd_register_uri_handler(server,&routes[i]));
    xTaskCreate(boot_check,"ota-check",4096,NULL,4,NULL);
}
