#include "cluster_rpc.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
_Static_assert(sizeof(rpc_header)==64,"wire header layout");
struct rpc_state { ts_state *model; uint32_t session,position,split; int active; };
rpc_state *rpc_open(ts_state *model) { rpc_state *s=calloc(1,sizeof *s);if(s)s->model=model;return s; }
void rpc_close(rpc_state *s) {free(s);}
void rpc_expire(rpc_state *s) {if(s){s->active=0;ts_reset(s->model);}}
int rpc_active(const rpc_state *s) {return s&&s->active;}
int rpc_dispatch(rpc_state *s,const void *request,size_t bytes,void *response,size_t cap) {
    if(!s||!request||!response||bytes<64||cap<64)return -1;
    rpc_header h;memcpy(&h,request,64);const ts_config *c=ts_config_get(s->model);
    if(h.magic!=RPC_MAGIC||h.status||!h.session||h.dim!=c->dim||h.bytes!=bytes-64||
       memcmp(h.model,ts_model_id(s->model),32)||!h.split||h.split>=c->layers)return -1;
    if(h.command==1) {
        if(s->active||h.bytes||h.position)return -1;
        ts_reset(s->model);s->active=1;s->session=h.session;s->position=0;s->split=h.split;
    } else {
        if(!s->active||h.session!=s->session||h.split!=s->split)return -1;
        if(h.command==2) {
            if(h.position!=s->position||h.position>=c->context||h.bytes!=c->dim*4||cap<bytes)return -1;
            const uint8_t *v=(const uint8_t*)request+64;
            for(unsigned i=0;i<c->dim;i++){float x;memcpy(&x,v+i*4,4);if(!isfinite(x))return -1;}
            memcpy(ts_x(s->model),v,h.bytes);
            if(ts_layers(s->model,(int)h.split,(int)c->layers,(int)h.position))return -1;
            memcpy((uint8_t*)response+64,ts_x(s->model),h.bytes);s->position++;
        } else if(h.command==3) {
            if(h.bytes)return -1;
            s->active=0;
        } else return -1;
    }
    h.status=0;memcpy(response,&h,64);return (int)(64+h.bytes);
}
