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
