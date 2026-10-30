#pragma once
#include <stddef.h>
#include <stdint.h>
/* Caller supplies a 128-byte header and the exact stored artifact length.
 * Zero means invalid. Does not allocate memory, read flash or execute a model. */
size_t ts_storage_expanded(const uint8_t *header,size_t stored);
