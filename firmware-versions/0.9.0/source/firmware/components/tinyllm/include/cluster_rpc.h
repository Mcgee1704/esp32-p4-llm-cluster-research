#pragma once
#include "tinyllm.h"
/* Little-endian IEEE754 protocol. Header is 64 bytes, payload <= dim * 4. */
#define RPC_MAGIC 0x31505250u
#define RPC_MAX_FRAME (64+1024*4)
typedef struct {
    uint32_t magic,command,session,position,split,dim,bytes,status;
    uint8_t model[32];
} rpc_header;
typedef struct rpc_state rpc_state;
rpc_state *rpc_open(ts_state *model);
void rpc_close(rpc_state *s);
void rpc_expire(rpc_state *s);
int rpc_active(const rpc_state *s);
int rpc_dispatch(rpc_state *s,const void *request,size_t bytes,void *response,size_t capacity);
