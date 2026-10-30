#include "dispatch_queue.h"
int dq_submit(dq_state *q,int64_t now) {
    int slot=-1;
    for(int i=0;i<DQ_CAPACITY;i++) {
        if(q->entries[i].state==DQ_FREE){slot=i;break;}
        if(q->entries[i].state>=DQ_DONE&&(slot<0||q->entries[i].sequence<q->entries[slot].sequence))slot=i;
    }
    if(slot>=0)q->entries[slot]=(dq_entry){.sequence=++q->sequence,.created_ms=now,.state=DQ_QUEUED,.lane=-1};
    return slot;
}
int dq_claim(dq_state *q,int lane) {
    if(lane<0||lane>1)return -1;
    int slot=-1;
    for(int i=0;i<DQ_CAPACITY;i++) {
        if(q->entries[i].state==DQ_RUNNING&&q->entries[i].lane==lane)return -1;
        if(q->entries[i].state==DQ_QUEUED&&(slot<0||q->entries[i].sequence<q->entries[slot].sequence))slot=i;
    }
    if(slot>=0){q->entries[slot].state=DQ_RUNNING;q->entries[slot].lane=lane;}
    return slot;
}
int dq_finish(dq_state *q,int slot,int state) {
    if(slot<0||slot>=DQ_CAPACITY||q->entries[slot].state!=DQ_RUNNING||(state!=DQ_DONE&&state!=DQ_FAILED))return -1;
    q->entries[slot].state=state;return 0;
}
int dq_cancel(dq_state *q,int slot) {
    if(slot<0||slot>=DQ_CAPACITY||q->entries[slot].state!=DQ_QUEUED)return -1;
    q->entries[slot].state=DQ_CANCELLED;return 0;
}
void dq_expire(dq_state *q,int64_t now,int64_t timeout) {
    for(int i=0;i<DQ_CAPACITY;i++)if(q->entries[i].state==DQ_QUEUED&&now-q->entries[i].created_ms>=timeout)q->entries[i].state=DQ_FAILED;
}
