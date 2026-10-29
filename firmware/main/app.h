#pragma once
#include "tinyllm.h"
#include "cluster_rpc.h"
#include "esp_err.h"
void lan_start(void);
void lan_stop(void);
void service_start(void);
void dispatcher_start(void);
int dispatcher_maintenance_begin(void);
void dispatcher_maintenance_end(void);
void model_load(void);
extern ts_state *model;
extern rpc_state *worker;
extern const char *model_error;
extern volatile int lan_ready;
extern volatile uint32_t lan_ip4;
