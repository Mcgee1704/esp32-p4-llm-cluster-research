#include "app.h"
#include "dispatch_queue.h"
#include "esp_http_server.h"
#include "esp_http_client.h"
#include "esp_timer.h"
#include "esp_random.h"
#include "esp_heap_caps.h"
#include "esp_app_desc.h"
#include "nvs.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "lwip/inet.h"
#include "lwip/sockets.h"
#include "lwip/tcp.h"
#include "cJSON.h"
#include "sdkconfig.h"
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <ctype.h>

/* This service never touches model/KV state. The existing port-80 HTTP task
 * remains the sole owner. Two forwarding tasks consume one shared FIFO. */
#define RESULT_CAP (160*1024)
#define WAIT_LIMIT_MS 180000
typedef struct {
    char id[17],body[2049],target[16],error[192],kernel[8];
    char *raw;size_t length;int tokens,received,boards;
    int64_t started_ms,finished_ms;
} dispatch_job;
typedef struct {char error[192];int healthy;int64_t retry_ms;} lane_state;
static dq_state queue;
static dispatch_job jobs[DQ_CAPACITY];
static lane_state lanes[2];
static SemaphoreHandle_t guard;
static TaskHandle_t tasks[2];
static char peer[16],model_id[65];
static int configured,maintenance;
static unsigned loaded_role,loaded_split,loaded_layers;
static char loaded_id[65];
static unsigned configuration_generation;
static uint32_t boot_id;
static const char *states[]={"free","queued","running","done","failed","cancelled"};
extern const unsigned char cluster_start[] asm("_binary_cluster_html_start");
extern const unsigned char cluster_end[] asm("_binary_cluster_html_end");
static int64_t now_ms(void){return esp_timer_get_time()/1000;}
static void lock(void){xSemaphoreTake(guard,portMAX_DELAY);}
static void unlock(void){xSemaphoreGive(guard);}
void dispatcher_model_changed(const ts_state *state) {
    if(guard)lock();
    loaded_role=state?ts_role(state):0;loaded_split=state?ts_end_layer(state):0;loaded_layers=state?ts_config_get(state)->layers:0;
    loaded_id[0]=0;if(state)for(int i=0;i<32;i++)sprintf(loaded_id+2*i,"%02x",ts_model_id(state)[i]);
    if(guard){configured=0;configuration_generation++;unlock();}
}
int dispatcher_model_peer(char out[16]) {
    if(!guard)return 0;
    lock();int ok=configured&&loaded_role==1&&*peer&&!strcmp(loaded_id,model_id);
    if(ok)snprintf(out,16,"%s",peer);
    unlock();return ok;
}
static void wake(void){for(int i=0;i<2;i++)if(tasks[i])xTaskNotifyGive(tasks[i]);}
static int active(void){int n=0;for(int i=0;i<DQ_CAPACITY;i++)n+=queue.entries[i].state==DQ_QUEUED||queue.entries[i].state==DQ_RUNNING;return n;}
int dispatcher_maintenance_begin(void) {
    if(!guard)return 1;
    lock();int ok=!maintenance&&!active();if(ok)maintenance=1;unlock();return ok;
}
void dispatcher_maintenance_end(void){if(guard){lock();maintenance=0;unlock();wake();}}
static esp_err_t reply_error(httpd_req_t *r,const char *code,const char *message) {
    httpd_resp_set_status(r,code);httpd_resp_set_type(r,"text/plain; charset=utf-8");
    return httpd_resp_sendstr(r,message);
}
static int authorized(httpd_req_t *r) {
    char supplied[129];size_t n=strlen(CONFIG_CLUSTER_KEY);unsigned diff=0;
    if(n<24||n>128||httpd_req_get_hdr_value_str(r,"X-Cluster-Key",supplied,sizeof supplied)!=ESP_OK||strlen(supplied)!=n) {
        reply_error(r,"401 Unauthorized","LAN key missing or invalid");return 0;
    }
    for(size_t i=0;i<n;i++)diff|=(unsigned char)supplied[i]^(unsigned char)CONFIG_CLUSTER_KEY[i];
    if(diff){reply_error(r,"401 Unauthorized","LAN key invalid");return 0;}return 1;
}
static esp_err_t json_reply(httpd_req_t *r,cJSON *json) {
    char *text=cJSON_PrintUnformatted(json);cJSON_Delete(json);
    if(!text)return reply_error(r,"500 Internal Server Error","Response allocation failed");
    httpd_resp_set_type(r,"application/json");httpd_resp_set_hdr(r,"Cache-Control","no-store");
    esp_err_t e=httpd_resp_sendstr(r,text);free(text);return e;
}
static cJSON *read_json(httpd_req_t *r) {
    if(!r->content_len||r->content_len>2048)return NULL;
    char body[2049];size_t at=0;
    while(at<r->content_len){int n=httpd_req_recv(r,body+at,r->content_len-at);if(n<=0)return NULL;at+=n;}
    body[at]=0;return cJSON_Parse(body);
}
static int valid_peer(const char *text) {
    struct in_addr ip;if(inet_pton(AF_INET,text,&ip)!=1||ip.s_addr==lan_ip4)return 0;
    uint32_t a=ntohl(ip.s_addr);
    return (a>>24)==10||(a>>20)==0xac1||(a>>16)==0xc0a8||(a>>16)==0xa9fe;
}
static void expire_jobs(void) {
    dq_expire(&queue,now_ms(),WAIT_LIMIT_MS);
    for(int i=0;i<DQ_CAPACITY;i++)if(queue.entries[i].state==DQ_FAILED&&!jobs[i].started_ms&&!jobs[i].error[0]) {
        snprintf(jobs[i].error,sizeof jobs[i].error,"Queue deadline exceeded; no available board");jobs[i].finished_ms=now_ms();
    }
}
typedef struct {char body[2048];size_t used;int overflow;} status_buffer;
static esp_err_t status_event(esp_http_client_event_t *event) {
    status_buffer *b=event->user_data;
    if(event->event_id==HTTP_EVENT_ON_CONNECTED){int one=1;setsockopt(esp_http_client_get_socket(event->client),IPPROTO_TCP,TCP_NODELAY,&one,sizeof one);}
    if(event->event_id==HTTP_EVENT_ON_DATA) {
        if(event->data_len<0||b->used+(size_t)event->data_len>=sizeof b->body)b->overflow=1;
        else{memcpy(b->body+b->used,event->data,event->data_len);b->used+=event->data_len;b->body[b->used]=0;}
    }
    return ESP_OK;
}
static int backend_status(const char *host,const char *expected,char found[65],char error[192],int role,int first,int end) {
    char url[80];snprintf(url,sizeof url,"http://%s/api/status",host);status_buffer buf={0};
    esp_http_client_config_t cfg={.url=url,.timeout_ms=2000,.disable_auto_redirect=true,.event_handler=status_event,.user_data=&buf};
    esp_http_client_handle_t c=esp_http_client_init(&cfg);
    if(!c){snprintf(error,192,"Backend client allocation failed");return 0;}
    esp_http_client_set_header(c,"X-Cluster-Key",CONFIG_CLUSTER_KEY);
    esp_err_t result=esp_http_client_perform(c);int status=esp_http_client_get_status_code(c);esp_http_client_cleanup(c);
    if(result!=ESP_OK||status!=200||buf.overflow){snprintf(error,192,"Backend unavailable or unauthorized (HTTP %d)",status);return 0;}
    cJSON *j=cJSON_Parse(buf.body);if(!j){snprintf(error,192,"Invalid backend status");return 0;}
    cJSON *id=cJSON_GetObjectItem(j,"model_id"),*protocol=cJSON_GetObjectItem(j,"dispatch_protocol");
    int ok=cJSON_IsTrue(cJSON_GetObjectItem(j,"model_ready"))&&!cJSON_IsTrue(cJSON_GetObjectItem(j,"worker_busy"))&&
        !cJSON_IsTrue(cJSON_GetObjectItem(j,"ota_pending"))&&cJSON_IsString(id)&&strlen(id->valuestring)==64&&
        cJSON_IsNumber(protocol)&&protocol->valueint==1;
    if(ok&&expected&&strcmp(id->valuestring,expected))ok=0;
    cJSON *r=cJSON_GetObjectItem(j,"role"),*f=cJSON_GetObjectItem(j,"first_layer"),*e=cJSON_GetObjectItem(j,"end_layer");
    int actual=cJSON_IsNumber(r)?r->valueint:0;
    if(ok&&role>=0&&actual!=role)ok=0;
    if(ok&&first>=0&&(!cJSON_IsNumber(f)||f->valueint!=first))ok=0;
    if(ok&&end>=0&&(!cJSON_IsNumber(e)||e->valueint!=end))ok=0;
    if(ok){if(found)memcpy(found,id->valuestring,65);error[0]=0;}
    else snprintf(error,192,"Backend busy, model mismatch, pending boot or unsupported protocol");
    cJSON_Delete(j);return ok;
}
static esp_err_t cluster_get(httpd_req_t *r) {
    if(!authorized(r))return ESP_OK;
    cJSON *j=cJSON_CreateObject();lock();expire_jobs();
    cJSON_AddStringToObject(j,"firmware",esp_app_get_description()->version);
    cJSON_AddBoolToObject(j,"configured",configured);cJSON_AddBoolToObject(j,"maintenance",maintenance);
    cJSON_AddStringToObject(j,"mode",loaded_role==1?"sharded":loaded_role==2?"worker":"replicated");
    cJSON_AddNumberToObject(j,"active_lanes",loaded_role==1?1:loaded_role==2?0:2);
    cJSON_AddStringToObject(j,"peer",peer);cJSON_AddStringToObject(j,"model_id",model_id);
    cJSON_AddNumberToObject(j,"capacity",DQ_CAPACITY);cJSON_AddNumberToObject(j,"waiting_limit_ms",WAIT_LIMIT_MS);
    int waiting=0,running=0;for(int i=0;i<DQ_CAPACITY;i++){waiting+=queue.entries[i].state==DQ_QUEUED;running+=queue.entries[i].state==DQ_RUNNING;}
    cJSON_AddNumberToObject(j,"queued",waiting);cJSON_AddNumberToObject(j,"running",running);
    cJSON_AddNumberToObject(j,"available_slots",DQ_CAPACITY-waiting-running);
    cJSON *ls=cJSON_AddArrayToObject(j,"lanes");
    for(int k=0;k<2;k++){cJSON *l=cJSON_CreateObject();cJSON_AddItemToArray(ls,l);
        cJSON_AddStringToObject(l,"target",k?peer:"local");cJSON_AddBoolToObject(l,"last_probe_ok",lanes[k].healthy);
        cJSON_AddStringToObject(l,"last_error",lanes[k].error);
        for(int i=0;i<DQ_CAPACITY;i++)if(queue.entries[i].state==DQ_RUNNING&&queue.entries[i].lane==k)cJSON_AddStringToObject(l,"active_job",jobs[i].id);
    }
    unlock();return json_reply(r,j);
}
static esp_err_t cluster_set(httpd_req_t *r) {
    if(!authorized(r))return ESP_OK;
    cJSON *j=read_json(r),*p=cJSON_GetObjectItem(j,"peer");
    if(!cJSON_IsString(p)||strlen(p->valuestring)>15||(*p->valuestring&&!valid_peer(p->valuestring))) {
        cJSON_Delete(j);return reply_error(r,"400 Bad Request","peer must be an empty string or another private LAN IPv4 address");
    }
    char proposed[16];snprintf(proposed,sizeof proposed,"%s",p->valuestring);cJSON_Delete(j);
    if(!dispatcher_maintenance_begin())return reply_error(r,"409 Conflict","Wait for or cancel active jobs before changing configuration");
    if(loaded_role==2||(loaded_role==1&&!*proposed)){dispatcher_maintenance_end();return reply_error(r,"409 Conflict","Coordinator requires layer worker; worker cannot dispatch");}
    char identity[65],reason[192];int ok=backend_status("127.0.0.1",NULL,identity,reason,(int)loaded_role,-1,-1);
    if(ok&&*proposed)ok=backend_status(proposed,identity,NULL,reason,loaded_role==1?2:0,loaded_role==1?(int)loaded_split:-1,loaded_role==1?(int)loaded_layers:-1);
    if(!ok){dispatcher_maintenance_end();return reply_error(r,"409 Conflict",reason);}
    nvs_handle_t nvs;esp_err_t e=nvs_open("dispatch",NVS_READWRITE,&nvs);
    if(e==ESP_OK){e=nvs_set_str(nvs,"peer",proposed);if(e==ESP_OK)e=nvs_set_str(nvs,"model",identity);if(e==ESP_OK)e=nvs_commit(nvs);nvs_close(nvs);}
    if(e!=ESP_OK){dispatcher_maintenance_end();return reply_error(r,"500 Internal Server Error","Could not save configuration");}
    lock();snprintf(peer,sizeof peer,"%s",proposed);memcpy(model_id,identity,65);configured=1;configuration_generation++;memset(lanes,0,sizeof lanes);unlock();
    dispatcher_maintenance_end();return cluster_get(r);
}
static esp_err_t job_submit(httpd_req_t *r) {
    if(!authorized(r))return ESP_OK;
    cJSON *j=read_json(r),*prompt=cJSON_GetObjectItem(j,"prompt"),*tokens=cJSON_GetObjectItem(j,"tokens");
    if(!cJSON_IsString(prompt)||strlen(prompt->valuestring)>1024||!cJSON_IsNumber(tokens)||tokens->valuedouble<1||tokens->valuedouble>128||tokens->valuedouble!=tokens->valueint) {
        cJSON_Delete(j);return reply_error(r,"400 Bad Request","Expected prompt up to 1024 bytes and integer tokens 1..128");
    }
    cJSON *kernel=cJSON_GetObjectItem(j,"kernel");
    if(kernel&&(!cJSON_IsString(kernel)||(strcmp(kernel->valuestring,"legacy")&&strcmp(kernel->valuestring,"paced")&&strcmp(kernel->valuestring,"dual")&&strcmp(kernel->valuestring,"sram")&&strcmp(kernel->valuestring,"tile4")))) {
        cJSON_Delete(j);return reply_error(r,"400 Bad Request","Invalid kernel mode");
    }
    char selected_kernel[8]={0};if(kernel)snprintf(selected_kernel,sizeof selected_kernel,"%s",kernel->valuestring);
    cJSON *body=cJSON_CreateObject();cJSON_AddStringToObject(body,"prompt",prompt->valuestring);cJSON_AddNumberToObject(body,"tokens",tokens->valueint);
    if(kernel)cJSON_AddStringToObject(body,"kernel",selected_kernel);
    int limit=tokens->valueint;cJSON_Delete(j);
    lock();expire_jobs();
    if(!configured||maintenance){unlock();cJSON_Delete(body);return reply_error(r,"503 Service Unavailable","Configure cluster first or wait for maintenance");}
    cJSON_AddStringToObject(body,"peer",loaded_role==1?peer:"");
    cJSON_AddStringToObject(body,"expected_model_id",model_id);char *encoded=cJSON_PrintUnformatted(body);cJSON_Delete(body);
    if(!encoded||strlen(encoded)>=sizeof jobs[0].body){unlock();free(encoded);return reply_error(r,"400 Bad Request","Encoded request too long");}
    char *raw=heap_caps_calloc(1,RESULT_CAP+1,MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT);
    if(!raw){unlock();free(encoded);return reply_error(r,"503 Service Unavailable","Insufficient result memory");}
    int slot=dq_submit(&queue,now_ms());
    if(slot<0){unlock();free(raw);free(encoded);return reply_error(r,"429 Too Many Requests","Queue capacity reached; no job accepted");}
    dispatch_job *job=&jobs[slot];free(job->raw);memset(job,0,sizeof *job);job->raw=raw;job->tokens=limit;job->boards=loaded_role==1?2:1;
    snprintf(job->id,sizeof job->id,"%08lx%08lx",(unsigned long)boot_id,(unsigned long)(uint32_t)queue.entries[slot].sequence);
    snprintf(job->kernel,sizeof job->kernel,"%s",selected_kernel);
    snprintf(job->body,sizeof job->body,"%s",encoded);free(encoded);
    cJSON *accepted=cJSON_CreateObject();cJSON_AddStringToObject(accepted,"id",job->id);cJSON_AddStringToObject(accepted,"state","queued");
    unlock();httpd_resp_set_status(r,"202 Accepted");wake();return json_reply(r,accepted);
}
static int find_job(const char *uri) {
    const char *id=uri+strlen("/api/jobs/");if(strlen(id)!=16)return -1;
    for(int i=0;i<DQ_CAPACITY;i++)if(queue.entries[i].state!=DQ_FREE&&!strcmp(jobs[i].id,id))return i;
    return -1;
}
static esp_err_t job_get(httpd_req_t *r) {
    if(!authorized(r))return ESP_OK;
    lock();expire_jobs();int i=find_job(r->uri);
    if(i<0){unlock();return reply_error(r,"404 Not Found","Job unknown, evicted or from an earlier boot");}
    dispatch_job *job=&jobs[i];dq_entry *entry=&queue.entries[i];cJSON *j=cJSON_CreateObject();
    cJSON_AddStringToObject(j,"id",job->id);cJSON_AddStringToObject(j,"state",states[entry->state]);
    cJSON_AddStringToObject(j,"target",job->target);cJSON_AddStringToObject(j,"error",job->error);
    cJSON_AddNumberToObject(j,"created_ms",entry->created_ms);cJSON_AddNumberToObject(j,"started_ms",job->started_ms);
    cJSON_AddNumberToObject(j,"finished_ms",job->finished_ms);cJSON_AddNumberToObject(j,"output_tokens",job->received);
    cJSON_AddNumberToObject(j,"queue_ms",(job->started_ms?job->started_ms:(job->finished_ms?job->finished_ms:now_ms()))-entry->created_ms);
    cJSON_AddStringToObject(j,"raw_ndjson",job->raw?job->raw:"");unlock();return json_reply(r,j);
}
static esp_err_t job_cancel(httpd_req_t *r) {
    if(!authorized(r))return ESP_OK;
    lock();int i=find_job(r->uri);
    if(i<0){unlock();return reply_error(r,"404 Not Found","Job unknown");}
    int result=dq_cancel(&queue,i);if(!result)jobs[i].finished_ms=now_ms();unlock();
    if(result)return reply_error(r,"409 Conflict","Only queued jobs can be cancelled");
    return job_get(r);
}
static int consume_line(int slot,char *line,int *done,char reason[192]) {
    cJSON *j=cJSON_Parse(line);if(!j){snprintf(reason,192,"Invalid backend NDJSON");return 0;}
    int ok=1;cJSON *token=cJSON_GetObjectItem(j,"token"),*hex=cJSON_GetObjectItem(j,"bytes_hex");
    if(*done)ok=0;
    else if(cJSON_IsNumber(token)&&cJSON_IsString(hex)) {
        size_t n=strlen(hex->valuestring);ok=n<=1024&&!(n%2);
        for(size_t k=0;ok&&k<n;k++)ok=isxdigit((unsigned char)hex->valuestring[k])!=0;
        if(ok){lock();jobs[slot].received++;ok=jobs[slot].received<=jobs[slot].tokens;unlock();}
    } else if(cJSON_IsTrue(cJSON_GetObjectItem(j,"done"))) {
        cJSON *count=cJSON_GetObjectItem(j,"output_tokens"),*boards=cJSON_GetObjectItem(j,"boards"),*error=cJSON_GetObjectItem(j,"error");
        lock();int received=jobs[slot].received;unlock();
        ok=!error&&cJSON_IsNumber(count)&&count->valueint==received&&cJSON_IsNumber(boards)&&boards->valueint==jobs[slot].boards;
        if(ok&&jobs[slot].kernel[0]) {
            cJSON *mode=cJSON_GetObjectItem(cJSON_GetObjectItem(j,"kernel"),"mode");
            ok=cJSON_IsString(mode)&&!strcmp(mode->valuestring,jobs[slot].kernel);
            if(!ok)snprintf(reason,192,"Backend did not execute requested kernel");
        }
        if(ok)*done=1;
        if(cJSON_IsString(error))snprintf(reason,192,"Backend: %.170s",error->valuestring);
    } else ok=0;
    cJSON_Delete(j);if(!ok&&!reason[0])snprintf(reason,192,"Invalid backend result or token count");return ok;
}
static int forward_job(int slot,const char *host,char reason[192]) {
    char url[80];snprintf(url,sizeof url,"http://%s/api/generate",host);
    esp_http_client_config_t cfg={.url=url,.method=HTTP_METHOD_POST,.timeout_ms=180000,.disable_auto_redirect=true};
    esp_http_client_handle_t c=esp_http_client_init(&cfg);if(!c){snprintf(reason,192,"Client allocation failed");return 0;}
    esp_http_client_set_header(c,"X-Cluster-Key",CONFIG_CLUSTER_KEY);esp_http_client_set_header(c,"Content-Type","application/json");
    int ok=0,done=0;size_t length=strlen(jobs[slot].body),at=0;
    if(esp_http_client_open(c,length)!=ESP_OK)goto finish;
    int one=1;if(setsockopt(esp_http_client_get_socket(c),IPPROTO_TCP,TCP_NODELAY,&one,sizeof one)<0)goto finish;
    while(at<length){int n=esp_http_client_write(c,jobs[slot].body+at,length-at);if(n<=0)goto finish;at+=n;}
    if(esp_http_client_fetch_headers(c)<0)goto finish;
    int status=esp_http_client_get_status_code(c);if(status!=200){snprintf(reason,192,"Backend HTTP %d; request not retried",status);goto finish;}
    char chunk[128],line[2048];size_t used=0;
    for(;;) {
        int n=esp_http_client_read(c,chunk,sizeof chunk);if(n<0)goto finish;if(!n)break;
        lock();dispatch_job *job=&jobs[slot];
        if(job->length+(size_t)n>RESULT_CAP){unlock();snprintf(reason,192,"Result capacity exceeded");goto finish;}
        memcpy(job->raw+job->length,chunk,n);job->length+=n;job->raw[job->length]=0;unlock();
        for(int k=0;k<n;k++) {
            if(chunk[k]=='\n'){line[used]=0;if(!consume_line(slot,line,&done,reason))goto finish;used=0;}
            else{if(used>=sizeof line-1){snprintf(reason,192,"Backend line too long");goto finish;}line[used++]=chunk[k];}
        }
    }
    ok=done&&!used&&esp_http_client_is_complete_data_received(c);
finish:
    esp_http_client_cleanup(c);if(!ok&&!reason[0])snprintf(reason,192,"Backend transfer interrupted; request not retried");return ok;
}
static void lane_task(void *arg) {
    int lane=(int)(intptr_t)arg;
    for(;;) {
        ulTaskNotifyTake(pdTRUE,pdMS_TO_TICKS(250));
        char host[16],identity[65],reason[192]={0};int waiting=0;
        lock();expire_jobs();for(int i=0;i<DQ_CAPACITY;i++)waiting+=queue.entries[i].state==DQ_QUEUED;
        unsigned generation=configuration_generation;
        int eligible=configured&&!maintenance&&loaded_role!=2&&(!lane||loaded_role!=1)&&waiting&&(!lane||(*peer&&valid_peer(peer)))&&now_ms()>=lanes[lane].retry_ms;
        snprintf(host,sizeof host,"%s",lane?peer:"127.0.0.1");memcpy(identity,model_id,65);unlock();
        if(!eligible)continue;
        int healthy=backend_status(host,identity,NULL,reason,(int)loaded_role,-1,-1);
        lock();if(generation!=configuration_generation){unlock();continue;}
        lanes[lane].healthy=healthy;snprintf(lanes[lane].error,sizeof lanes[lane].error,"%s",reason);
        if(!healthy){lanes[lane].retry_ms=now_ms()+3000;unlock();continue;}
        int slot=maintenance?-1:dq_claim(&queue,lane);
        if(slot>=0){jobs[slot].started_ms=now_ms();snprintf(jobs[slot].target,sizeof jobs[slot].target,"%s",lane?host:"local");}
        unlock();if(slot<0)continue;
        int ok=forward_job(slot,host,reason);
        lock();jobs[slot].finished_ms=now_ms();snprintf(jobs[slot].error,sizeof jobs[slot].error,"%s",reason);
        dq_finish(&queue,slot,ok?DQ_DONE:DQ_FAILED);
        if(!ok){lanes[lane].healthy=0;lanes[lane].retry_ms=now_ms()+3000;snprintf(lanes[lane].error,sizeof lanes[lane].error,"%s",reason);}
        unlock();wake();
    }
}
static esp_err_t index_page(httpd_req_t *r){httpd_resp_set_type(r,"text/html; charset=utf-8");httpd_resp_set_hdr(r,"Cache-Control","no-store");return httpd_resp_send(r,(const char*)cluster_start,cluster_end-cluster_start);}
static esp_err_t socket_open(httpd_handle_t server,int socket){(void)server;int one=1;return setsockopt(socket,IPPROTO_TCP,TCP_NODELAY,&one,sizeof one)<0?ESP_FAIL:ESP_OK;}
void dispatcher_start(void) {
    guard=xSemaphoreCreateMutex();ESP_ERROR_CHECK(guard?ESP_OK:ESP_ERR_NO_MEM);boot_id=esp_random();
    nvs_handle_t nvs;if(nvs_open("dispatch",NVS_READONLY,&nvs)==ESP_OK){size_t a=sizeof peer,b=sizeof model_id;
        configured=nvs_get_str(nvs,"peer",peer,&a)==ESP_OK&&nvs_get_str(nvs,"model",model_id,&b)==ESP_OK&&strlen(model_id)==64;
        nvs_close(nvs);}
    if(strcmp(model_id,loaded_id)||loaded_role==2||(loaded_role==1&&!*peer))configured=0;
    httpd_config_t cfg=HTTPD_DEFAULT_CONFIG();cfg.server_port=8081;cfg.ctrl_port=32769;cfg.stack_size=8192;
    cfg.max_open_sockets=10;cfg.max_uri_handlers=8;cfg.lru_purge_enable=true;cfg.uri_match_fn=httpd_uri_match_wildcard;cfg.open_fn=socket_open;
    httpd_handle_t server;ESP_ERROR_CHECK(httpd_start(&server,&cfg));
    const httpd_uri_t routes[]={
        {.uri="/",.method=HTTP_GET,.handler=index_page},
        {.uri="/api/cluster",.method=HTTP_GET,.handler=cluster_get},
        {.uri="/api/cluster",.method=HTTP_POST,.handler=cluster_set},
        {.uri="/api/jobs",.method=HTTP_POST,.handler=job_submit},
        {.uri="/api/jobs/*",.method=HTTP_GET,.handler=job_get},
        {.uri="/api/jobs/*",.method=HTTP_DELETE,.handler=job_cancel}};
    for(size_t i=0;i<sizeof routes/sizeof routes[0];i++)ESP_ERROR_CHECK(httpd_register_uri_handler(server,&routes[i]));
    for(int i=0;i<2;i++)ESP_ERROR_CHECK(xTaskCreate(lane_task,i?"dispatch-peer":"dispatch-local",8192,(void*)(intptr_t)i,4,&tasks[i])==pdPASS?ESP_OK:ESP_ERR_NO_MEM);
}
