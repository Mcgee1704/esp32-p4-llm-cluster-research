#pragma once
#include <stdint.h>
#define DQ_CAPACITY 8
enum {DQ_FREE,DQ_QUEUED,DQ_RUNNING,DQ_DONE,DQ_FAILED,DQ_CANCELLED};
typedef struct {uint64_t sequence;int64_t created_ms;int state,lane;} dq_entry;
typedef struct {uint64_t sequence;dq_entry entries[DQ_CAPACITY];} dq_state;
/* Caller must serialize all operations; this core owns no model or pointers. */
int dq_submit(dq_state *q,int64_t now_ms);
int dq_claim(dq_state *q,int lane);
int dq_finish(dq_state *q,int slot,int state);
int dq_cancel(dq_state *q,int slot);
void dq_expire(dq_state *q,int64_t now_ms,int64_t timeout_ms);
