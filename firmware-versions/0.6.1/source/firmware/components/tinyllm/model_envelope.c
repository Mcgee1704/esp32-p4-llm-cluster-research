#include "model_envelope.h"
#include <string.h>
static uint32_t u32(const uint8_t *p){uint32_t n;memcpy(&n,p,4);return n;}
size_t ts_storage_expanded(const uint8_t *h,size_t stored) {
    if(!h||stored<128||stored>32u*1024*1024||u32(h+36)>stored-128||u32(h+40)!=stored-128-u32(h+36))return 0;
    if(!memcmp(h,"P4ZL0001",8)) {
        size_t expanded=u32(h+8);
        if(expanded<256||expanded>32u*1024*1024||u32(h+40)||u32(h+44)||!u32(h+36))return 0;
        for(int i=12;i<36;i++)if(h[i])return 0;
        for(int i=116;i<128;i++)if(h[i])return 0;
        return expanded;
    }
    if(memcmp(h,"P4QS0001",8)&&memcmp(h,"P4LM0001",8)&&memcmp(h,"P4GN0001",8))return 0;
    return stored;
}
