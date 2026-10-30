#pragma once
#include "esp_partition.h"
#include <stddef.h>
#include <stdint.h>

/* Expanded bytes live in PSRAM. On-flash compression never changes INT4 data. */
int model_storage_header(const uint8_t header[128],size_t stored,size_t *expanded);
void *model_storage_read(const esp_partition_t *partition,const uint8_t header[128],size_t stored,const char **error);
