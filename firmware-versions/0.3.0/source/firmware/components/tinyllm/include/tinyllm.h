#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct ts_state ts_state;
typedef struct { uint32_t dim,hidden,layers,heads,kv_heads,vocab,context; } ts_config;
/* Blob must remain alive and 4-byte aligned. One state supports one request. */
ts_state *ts_open(const void *blob, size_t bytes);
void ts_close(ts_state *s);
const ts_config *ts_config_get(const ts_state *s);
const uint8_t *ts_model_id(const ts_state *s);
void ts_reset(ts_state *s);
int ts_embed(ts_state *s, int token);
int ts_layers(ts_state *s, int first, int end, int position);
float *ts_x(ts_state *s);
float *ts_finish(ts_state *s);
int ts_argmax(ts_state *s);
int ts_encode(ts_state *s, const char *text, int *tokens, int capacity);
const char *ts_decode(ts_state *s, int previous, int token);
uint32_t ts_crc32(const void *data, size_t bytes);

/* Kernel choice is per state, changed only by its single inference owner. */
enum { TS_KERNEL_LEGACY, TS_KERNEL_PACED, TS_KERNEL_DUAL };
#define TS_KERNEL_DEFAULT TS_KERNEL_DUAL
typedef struct {
    uint64_t matmul_us, finish_us, pause_us, pause_calls, rows;
    uint64_t helper_us, helper_pause_us, helper_pause_calls, helper_rows, parallel_calls;
    uint64_t barrier_us, overlap_us;
    uint32_t owner_core_mask, helper_core_mask;
} ts_kernel_profile;
int ts_set_kernel(ts_state *s, int mode);
int ts_get_kernel(const ts_state *s);
const ts_kernel_profile *ts_get_kernel_profile(const ts_state *s);
