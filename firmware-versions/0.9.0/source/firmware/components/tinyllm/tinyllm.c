#include "int4_dot.h"
/* Portable scalar Llama inference. Algorithm reference: karpathy/llama2.c (MIT).
 * New P4LM parser, per-row INT8 layout and layer-range API; see THIRD_PARTY.md. */
#include "tinyllm.h"
#include "gpt2_tokenizer.h"
#include "sp_tokenizer.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "esp_memory_utils.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "esp_timer.h"
#define ALLOC(n) heap_caps_calloc(1,(n),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)
#define YIELD() vTaskDelay(1)
#else
#define ALLOC(n) calloc(1,(n))
#define YIELD() ((void)0)
#endif
typedef struct { const float *scale; const int8_t *q; int rows,cols,bits; } matrix;
typedef struct { const float *na,*nf,*ba,*bf,*bo,*b1,*b2,*qn,*kn; matrix q,k,v,o,w1,w2,w3; } layer;
typedef struct { const char *text; int id; } token_index;
typedef struct {
    float *out; const matrix *m; const float *x; int first,end,mode;
    int64_t next_pause,started,finished; uint64_t pause_us,pause_calls; uint32_t core_mask;
} row_work;
#ifdef ESP_PLATFORM
typedef struct {
    SemaphoreHandle_t start,done; TaskHandle_t task; int stop; row_work work;
} parallel_context;
static int parallel_open(ts_state *s);
static void parallel_close(ts_state *s);
#endif
struct ts_state {
    int kernel; int64_t next_pause,helper_next_pause; ts_kernel_profile profile;
#ifdef ESP_PLATFORM
    parallel_context *parallel;
#endif
    ts_config c; const uint8_t *blob; matrix emb,positions; layer layer[32]; const float *norm,*norm_bias;
    int neo,sharded; unsigned role,first,end,architecture,extra_eos; float epsilon,theta; unsigned window,eos;gpt2_tokenizer *bpe;sp_tokenizer *spm;char decoded[513];
    float *x,*xb,*xb2,*hb,*hb2,*q,*att,*logits,*kc,*vc;
    float *work_psram[6],*work_internal;
    char **tokens; float *scores; token_index *sorted; char *strings;
    int next_position; char byte_piece[256][2];
};
uint32_t ts_crc32(const void *data,size_t n) {
    uint32_t crc=~0u; const uint8_t *p=data;
    while(n--) { crc^=*p++; for(int j=0;j<8;j++) crc=(crc>>1)^((0u-(crc&1u))&0xedb88320u); if((n&65535)==0)YIELD(); }
    return ~crc;
}
static uint32_t u32(const uint8_t *p) { uint32_t x; memcpy(&x,p,4); return x; }
static const void *take(const uint8_t **p,const uint8_t *end,size_t n) {
    if(n>(size_t)(end-*p)) return NULL;
    const void *r=*p; *p+=n; return r;
}
static int read_matrix_bits(matrix *m,const uint8_t **p,const uint8_t *end,int r,int c,int bits) {
    m->rows=r; m->cols=c;m->bits=bits;
    m->scale=take(p,end,(size_t)r*4); if(!m->scale) return -1;
    for(int i=0;i<r;i++) if(!isfinite(m->scale[i])||m->scale[i]<=0) return -1;
    m->q=take(p,end,(size_t)r*c*bits/8); return m->q?0:-1;
}
static int read_matrix(matrix *m,const uint8_t **p,const uint8_t *end,int r,int c) { return read_matrix_bits(m,p,end,r,c,8); }
static int token_cmp(const void *a,const void *b) {
    return strcmp(((const token_index*)a)->text,((const token_index*)b)->text);
}
static const float *read_vector(const uint8_t **p,const uint8_t *end,unsigned count) {
    const float *v=take(p,end,(size_t)count*4);if(!v)return NULL;
    for(unsigned i=0;i<count;i++)if(!isfinite(v[i]))return NULL;
    return v;
}
ts_state *ts_open(const void *blob,size_t bytes) {
    const uint8_t *b=blob;
    if(!b||((uintptr_t)b&3)||bytes<128) return NULL;
    int neo=!memcmp(b,"P4GN0001",8);
    int qs=!memcmp(b,"P4QS0001",8);
    if(!neo&&!qs&&memcmp(b,"P4LM0001",8))return NULL;
    ts_config c; memcpy(&c,b+8,sizeof c);
    if(!c.dim||c.dim>1024||c.dim%4||!c.hidden||c.hidden>4096||c.hidden%4||
       !c.layers||c.layers>32||!c.heads||c.heads>c.dim||!c.kv_heads||c.kv_heads>c.heads||
       c.heads%c.kv_heads||c.dim%c.heads||(c.dim/c.heads)%2||
       c.vocab<259||c.vocab>65536||!c.context||c.context>1024) return NULL;
    size_t weights=u32(b+36),toksize=u32(b+40);
    if(weights>bytes-128||toksize!=bytes-128-weights||weights%4||
       ts_crc32(b+128,bytes-128)!=u32(b+80)) return NULL;
    ts_state *s=calloc(1,sizeof *s); if(!s) return NULL;
    s->kernel=TS_KERNEL_PACED; s->c=c; s->blob=b;s->neo=neo;s->sharded=qs;
    s->end=c.layers;s->epsilon=1e-5f;s->theta=10000.f;
    const uint8_t *p=b+128,*end=p+weights;
    int d=(int)c.dim,h=(int)c.hidden,kd=d*(int)c.kv_heads/(int)c.heads;
    if(qs) {
        const uint8_t *meta=take(&p,end,128);if(!meta)goto fail;
        s->role=u32(b+44);s->architecture=u32(meta+36);s->first=u32(meta+40);s->end=u32(meta+44);
        s->eos=u32(meta+52);s->extra_eos=u32(meta+56);memcpy(&s->epsilon,meta+60,4);memcpy(&s->theta,meta+64,4);
        if(u32(meta+32)!=1||!s->architecture||s->architecture>2||s->role>2||u32(meta+48)!=4||
           s->first>=s->end||s->end>c.layers||s->eos>=c.vocab||
           (s->extra_eos!=UINT32_MAX&&s->extra_eos>=c.vocab)||
           !isfinite(s->epsilon)||s->epsilon<=0||s->epsilon>.01f||!isfinite(s->theta)||s->theta<100||s->theta>1e8f||
           u32(meta+68)>1||u32(meta+72)<c.context||
           (s->role==0&&(s->first||s->end!=c.layers))||
           (s->role==1&&(s->first||s->end>=c.layers))||
           (s->role==2&&(!s->first||s->end!=c.layers||toksize))||
           (s->role!=2&&!toksize))goto fail;
        for(int i=76;i<128;i++)if(meta[i])goto fail;
        for(int i=84;i<128;i++)if(b[i])goto fail;
        if(s->role!=2&&read_matrix_bits(&s->emb,&p,end,(int)c.vocab,d,4))goto fail;
        for(unsigned i=s->first;i<s->end;i++) {
            layer *l=&s->layer[i];l->na=read_vector(&p,end,c.dim);l->nf=read_vector(&p,end,c.dim);
            if(!l->na||!l->nf||read_matrix_bits(&l->q,&p,end,d,d,4)||read_matrix_bits(&l->k,&p,end,kd,d,4)||
               read_matrix_bits(&l->v,&p,end,kd,d,4)||read_matrix_bits(&l->o,&p,end,d,d,4)||
               read_matrix_bits(&l->w1,&p,end,h,d,4)||read_matrix_bits(&l->w2,&p,end,d,h,4)||
               read_matrix_bits(&l->w3,&p,end,h,d,4))goto fail;
            if(s->architecture==2){l->qn=read_vector(&p,end,c.dim/c.heads);l->kn=read_vector(&p,end,c.dim/c.heads);if(!l->qn||!l->kn)goto fail;}
        }
        if(s->role!=2){s->norm=read_vector(&p,end,c.dim);if(!s->norm)goto fail;}
        if(p!=end)goto fail;
        if(s->role!=2){
            if(toksize>=8&&!memcmp(end,"SPBP0001",8)){s->spm=sp_open(end,toksize,c.vocab,s->eos);if(!s->spm)goto fail;}
            else{s->bpe=gpt2_open(end,toksize,c.vocab,s->eos);if(!s->bpe)goto fail;}
        }
    } else if(neo) {
        const uint8_t *meta=take(&p,end,12);if(!meta||c.kv_heads!=c.heads||u32(b+44))goto fail;
        unsigned positions=u32(meta);s->window=u32(meta+4);s->eos=u32(meta+8);
        if(positions<c.context||positions>2048||!s->window||s->window>2048||s->eos>=c.vocab)goto fail;
        if(read_matrix(&s->emb,&p,end,(int)c.vocab,d)||read_matrix(&s->positions,&p,end,(int)positions,d))goto fail;
        for(unsigned i=0;i<c.layers;i++) {
            layer *l=&s->layer[i];
            l->na=read_vector(&p,end,c.dim);l->ba=read_vector(&p,end,c.dim);
            if(!l->na||!l->ba||read_matrix(&l->q,&p,end,d,d)||read_matrix(&l->k,&p,end,d,d)||
               read_matrix(&l->v,&p,end,d,d)||read_matrix(&l->o,&p,end,d,d))goto fail;
            l->bo=read_vector(&p,end,c.dim);l->nf=read_vector(&p,end,c.dim);l->bf=read_vector(&p,end,c.dim);
            if(!l->bo||!l->nf||!l->bf||read_matrix(&l->w1,&p,end,h,d))goto fail;
            l->b1=read_vector(&p,end,c.hidden);if(!l->b1||read_matrix(&l->w2,&p,end,d,h))goto fail;
            l->b2=read_vector(&p,end,c.dim);if(!l->b2)goto fail;
        }
        s->norm=read_vector(&p,end,c.dim);s->norm_bias=read_vector(&p,end,c.dim);
        if(!s->norm||!s->norm_bias||p!=end)goto fail;
        s->bpe=gpt2_open(end,toksize,c.vocab,s->eos);if(!s->bpe)goto fail;
    } else {
    if(read_matrix(&s->emb,&p,end,(int)c.vocab,d)) goto fail;
    for(unsigned i=0;i<c.layers;i++) {
        layer *l=&s->layer[i]; l->na=take(&p,end,c.dim*4); l->nf=take(&p,end,c.dim*4);
        if(!l->na||!l->nf) goto fail;
        for(int j=0;j<d;j++) if(!isfinite(l->na[j])||!isfinite(l->nf[j])) goto fail;
        if(read_matrix(&l->q,&p,end,d,d)||read_matrix(&l->k,&p,end,kd,d)||
           read_matrix(&l->v,&p,end,kd,d)||read_matrix(&l->o,&p,end,d,d)||
           read_matrix(&l->w1,&p,end,h,d)||read_matrix(&l->w2,&p,end,d,h)||
           read_matrix(&l->w3,&p,end,h,d)) goto fail;
    }
    s->norm=take(&p,end,c.dim*4); if(!s->norm||p!=end) goto fail;
    for(int j=0;j<d;j++) if(!isfinite(s->norm[j])) goto fail;
    s->tokens=ALLOC(c.vocab*sizeof(char*)); s->scores=ALLOC(c.vocab*4);
    s->sorted=ALLOC(c.vocab*sizeof(token_index)); s->strings=ALLOC(toksize+c.vocab);
    if(!s->tokens||!s->scores||!s->sorted||!s->strings) goto fail;
    p=end; end=b+bytes;
    const uint8_t *maxlen=take(&p,end,4);
    if(!maxlen||!u32(maxlen)||u32(maxlen)>512) goto fail;
    char *dest=s->strings;
    for(unsigned i=0;i<c.vocab;i++) {
        const uint8_t *entry=take(&p,end,8); if(!entry) goto fail;
        uint32_t n=u32(entry+4); const char *str=take(&p,end,n);
        memcpy(&s->scores[i],entry,4);
        if(!str||!n||n>512||memchr(str,0,n)||!isfinite(s->scores[i])) goto fail;
        memcpy(dest,str,n); dest[n]=0; s->tokens[i]=dest;
        s->sorted[i]=(token_index){dest,(int)i}; dest+=n+1;
    }
    if(p!=end) goto fail;
    qsort(s->sorted,c.vocab,sizeof(token_index),token_cmp);
    }
    if(!neo&&!qs)for(unsigned i=1;i<c.vocab;i++) if(!strcmp(s->sorted[i-1].text,s->sorted[i].text)) goto fail;
    for(int i=0;i<256;i++) s->byte_piece[i][0]=(char)i;
    s->x=ALLOC(c.dim*4); s->xb=ALLOC(c.dim*4); s->xb2=ALLOC(c.dim*4);
    s->hb=ALLOC(c.hidden*4); s->hb2=ALLOC(c.hidden*4); s->q=ALLOC(c.dim*4);
    s->work_psram[0]=s->x;s->work_psram[1]=s->xb;s->work_psram[2]=s->xb2;
    s->work_psram[3]=s->q;s->work_psram[4]=s->hb;s->work_psram[5]=s->hb2;
    s->att=ALLOC(c.heads*c.context*4); if(s->role!=2)s->logits=ALLOC(c.vocab*4);
    size_t cache=(size_t)(s->end-s->first)*c.context*(unsigned)kd*4;
    s->kc=ALLOC(cache); s->vc=ALLOC(cache);
    if(!s->x||!s->xb||!s->xb2||!s->hb||!s->hb2||!s->q||!s->att||(s->role!=2&&!s->logits)||!s->kc||!s->vc) goto fail;
    if(ts_set_kernel(s,TS_KERNEL_DEFAULT))goto fail;
    return s;
fail: ts_close(s); return NULL;
}
void ts_close(ts_state *s) {
    if(!s) return;
#ifdef ESP_PLATFORM
    parallel_close(s);
#endif
    for(int i=0;i<6;i++)free(s->work_psram[i]);
    free(s->work_internal);
    free(s->att);free(s->logits);free(s->kc);free(s->vc);free(s->tokens);
    free(s->scores);free(s->sorted);free(s->strings);gpt2_close(s->bpe);sp_close(s->spm);free(s);
}
const ts_config *ts_config_get(const ts_state *s) { return &s->c; }
const uint8_t *ts_model_id(const ts_state *s) { return s->sharded?s->blob+128:s->blob+48; }
const uint8_t *ts_artifact_id(const ts_state *s){return s->blob+48;}
unsigned ts_role(const ts_state *s){return s->role;}
unsigned ts_first_layer(const ts_state *s){return s->first;}
unsigned ts_end_layer(const ts_state *s){return s->end;}
unsigned ts_quant_bits(const ts_state *s){return s->sharded?4:8;}
const char *ts_architecture(const ts_state *s){return s->neo?"gpt_neo":s->architecture==2?"qwen3":"llama";}
const char *ts_tokenizer_kind(const ts_state *s){return s->spm?"metaspace_bpe":s->bpe?"byte_bpe":s->role==2?"none":"legacy_vocab";}
int ts_is_eos(const ts_state *s,int token){return s->sharded?((unsigned)token==s->eos||(unsigned)token==s->extra_eos):s->neo?(unsigned)token==s->eos:token==1||token==2;}
static int64_t now_us(void) {
#ifdef ESP_PLATFORM
    return esp_timer_get_time();
#else
    return 0;
#endif
}
size_t ts_internal_work_bytes(const ts_state *s) {
    return s->work_internal?((size_t)4*s->c.dim+2*s->c.hidden)*sizeof(float):0;
}
int ts_work_is_internal(const ts_state *s) {
#ifdef ESP_PLATFORM
    return s->x&&esp_ptr_internal(s->x)&&esp_ptr_internal(s->xb)&&esp_ptr_internal(s->xb2)&&
        esp_ptr_internal(s->q)&&esp_ptr_internal(s->hb)&&esp_ptr_internal(s->hb2);
#else
    return s->work_internal&&s->x==s->work_internal;
#endif
}
static int select_work(ts_state *s,int internal) {
    size_t bytes=((size_t)4*s->c.dim+2*s->c.hidden)*sizeof(float);
    if(internal&&!s->work_internal) {
#ifdef ESP_PLATFORM
        s->work_internal=heap_caps_calloc(1,bytes,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
#else
        s->work_internal=calloc(1,bytes);
#endif
        if(!s->work_internal)return -1;
    }
    float **current[]={&s->x,&s->xb,&s->xb2,&s->q,&s->hb,&s->hb2};size_t offset=0;
    for(int i=0;i<6;i++) {
        size_t count=i<4?s->c.dim:s->c.hidden;
        float *target=internal?s->work_internal+offset:s->work_psram[i];
        /* Preserve live activations when switching banks; KV stays in PSRAM. */
        if(target!=*current[i])memcpy(target,*current[i],count*sizeof(float));
        *current[i]=target;offset+=count;
    }
    return 0;
}
int ts_set_kernel(ts_state *s,int mode) {
    if(mode<TS_KERNEL_LEGACY||mode>TS_KERNEL_TILE4)return -1;
#ifdef ESP_PLATFORM
    if(mode>=TS_KERNEL_DUAL&&parallel_open(s))return -1;
#endif
    if(select_work(s,mode>=TS_KERNEL_SRAM))return -1;
    s->kernel=mode;return 0;
}
int ts_get_kernel(const ts_state *s) {return s->kernel;}
const ts_kernel_profile *ts_get_kernel_profile(const ts_state *s) {return &s->profile;}
void ts_reset(ts_state *s) {
    memset(&s->profile,0,sizeof s->profile);s->next_pause=s->helper_next_pause=now_us()+10000;
    s->next_position=0;
    /* Stale cache is never read: all positions through the current one are overwritten. */
    memset(s->x,0,s->c.dim*4);
}
float *ts_x(ts_state *s) { return s->x; }
static void rms(float *out,const float *x,const float *w,int n,float epsilon) {
    float sum=0; for(int i=0;i<n;i++) sum+=x[i]*x[i];
    float inv=1.0f/sqrtf(sum/n+epsilon);
    for(int i=0;i<n;i++) out[i]=w[i]*(x[i]*inv);
}
static void norm(ts_state *s,float *out,const float *x,const float *w,const float *bias,int n) {
    if(!s->neo){rms(out,x,w,n,s->epsilon);return;}
    float mean=0;for(int i=0;i<n;i++)mean+=x[i];mean/=n;
    float variance=0;for(int i=0;i<n;i++){float z=x[i]-mean;variance+=z*z;}
    float inv=1.0f/sqrtf(variance/n+1e-5f);
    for(int i=0;i<n;i++)out[i]=((x[i]-mean)*inv)*w[i]+bias[i];
}
/* Each row keeps exactly the scalar summation order. Only complete rows move
 * to the helper; inputs are immutable until its completion semaphore arrives. */
static int quant_at(const int8_t *p,int j,int bits) {
    if(bits==8)return p[j];
    int v=((const uint8_t*)p)[j/2]>>((j&1)*4);v&=15;return v<8?v:v-16;
}
static void calculate_rows(row_work *w) {
    const matrix *m=w->m;w->started=now_us();
    for(int i=w->first;i<w->end;) {
        if(w->mode==TS_KERNEL_TILE4&&i+3<w->end) {
            size_t stride=(size_t)m->cols*m->bits/8;
            const int8_t *q0=m->q+(size_t)i*stride,*q1=q0+stride,*q2=q1+stride,*q3=q2+stride;
            float a=0,b=0,c=0,d=0;
            if(m->bits==4) {
                float sums[4];
                ts_int4_dot4(sums,(const uint8_t*)q0,(const uint8_t*)q1,
                             (const uint8_t*)q2,(const uint8_t*)q3,w->x,m->cols);
                a=sums[0];b=sums[1];c=sums[2];d=sums[3];
            } else for(int j=0;j<m->cols;j++) {
                float x=w->x[j];
                a+=(float)q0[j]*x;b+=(float)q1[j]*x;c+=(float)q2[j]*x;d+=(float)q3[j]*x;
            }
            w->out[i]=a*m->scale[i];w->out[i+1]=b*m->scale[i+1];
            w->out[i+2]=c*m->scale[i+2];w->out[i+3]=d*m->scale[i+3];i+=4;
        } else {
            float sum=0;const int8_t *q=m->q+(size_t)i*m->cols*m->bits/8;
            for(int j=0;j<m->cols;j++)sum+=(float)quant_at(q,j,m->bits)*w->x[j];
            w->out[i]=sum*m->scale[i];i++;
        }
#ifdef ESP_PLATFORM
        if((w->mode==TS_KERNEL_LEGACY&&(i&255)==0)||
           (w->mode!=TS_KERNEL_LEGACY&&(i&31)==0&&now_us()>=w->next_pause)) {
            int64_t before=now_us();YIELD();
            int64_t after=now_us();w->pause_us+=after-before;w->pause_calls++;
            w->next_pause=after+10000;
        }
#endif
    }
    w->finished=now_us();
#ifdef ESP_PLATFORM
    w->core_mask=1u<<xPortGetCoreID();
#endif
}
#ifdef ESP_PLATFORM
static void parallel_task(void *arg) {
    parallel_context *p=arg;
    for(;;) {
        xSemaphoreTake(p->start,portMAX_DELAY);
        if(p->stop) {
            /* After signalling, never access p again: owner may release it. */
            xSemaphoreGive(p->done);vTaskDelete(NULL);return;
        }
        calculate_rows(&p->work);
        xSemaphoreGive(p->done);
    }
}
static int parallel_open(ts_state *s) {
    if(s->parallel)return 0;
    parallel_context *p=calloc(1,sizeof *p);if(!p)return -1;
    p->start=xSemaphoreCreateBinary();p->done=xSemaphoreCreateBinary();
    if(!p->start||!p->done)goto fail;
    /* The HTTP inference owner is pinned to core 1; helper runs on core 0. */
    if(xTaskCreatePinnedToCore(parallel_task,"matrix-helper",4096,p,5,&p->task,0)!=pdPASS)goto fail;
    s->parallel=p;return 0;
fail:
    if(p->start)vSemaphoreDelete(p->start);
    if(p->done)vSemaphoreDelete(p->done);
    free(p);return -1;
}
static void parallel_close(ts_state *s) {
    parallel_context *p=s->parallel;if(!p)return;
    /* Single-owner API guarantees there is no in-flight matrix at close. */
    p->stop=1;xSemaphoreGive(p->start);xSemaphoreTake(p->done,portMAX_DELAY);
    vSemaphoreDelete(p->start);vSemaphoreDelete(p->done);free(p);s->parallel=NULL;
}
#endif
static void matmul(ts_state *s,float *out,const matrix *m,const float *x) {
    int64_t started=now_us();
    row_work own={.out=out,.m=m,.x=x,.end=m->rows,.mode=s->kernel,.next_pause=s->next_pause};
    if(s->kernel>=TS_KERNEL_DUAL&&m->rows>=128) {
        int split=(m->rows/2)&~31;own.end=split;
        row_work helper={.out=out,.m=m,.x=x,.first=split,.end=m->rows,
                         .mode=s->kernel,.next_pause=s->helper_next_pause};
#ifdef ESP_PLATFORM
        s->parallel->work=helper;xSemaphoreGive(s->parallel->start);
        calculate_rows(&own);
        int64_t wait_started=now_us();xSemaphoreTake(s->parallel->done,portMAX_DELAY);
        s->profile.barrier_us+=now_us()-wait_started;
        helper=s->parallel->work;
#else
        /* Portable tests exercise identical row partitions, not concurrency. */
        calculate_rows(&own);calculate_rows(&helper);
#endif
        s->helper_next_pause=helper.next_pause;
        s->profile.helper_us+=helper.finished-helper.started;
        s->profile.helper_pause_us+=helper.pause_us;s->profile.helper_pause_calls+=helper.pause_calls;
        s->profile.helper_rows+=helper.end-helper.first;s->profile.parallel_calls++;
        s->profile.helper_core_mask|=helper.core_mask;
        int64_t begin=own.started>helper.started?own.started:helper.started;
        int64_t end=own.finished<helper.finished?own.finished:helper.finished;
        if(end>begin)s->profile.overlap_us+=end-begin;
    } else calculate_rows(&own);
    s->next_pause=own.next_pause;s->profile.pause_us+=own.pause_us;s->profile.pause_calls+=own.pause_calls;
    s->profile.owner_core_mask|=own.core_mask;
    s->profile.matmul_us+=now_us()-started;s->profile.rows+=m->rows;
}
int ts_embed(ts_state *s,int token) {
    if(s->role==2||token<0||(unsigned)token>=s->c.vocab) return -1;
    const int8_t *q=s->emb.q+(size_t)token*s->c.dim*s->emb.bits/8;
    for(unsigned j=0;j<s->c.dim;j++) s->x[j]=quant_at(q,(int)j,s->emb.bits)*s->emb.scale[token];
    return 0;
}
int ts_layers(ts_state *s,int first,int end,int pos) {
    if(first<0||(unsigned)first<s->first||end<=first||(unsigned)end>s->end||pos<0||
       (unsigned)pos>=s->c.context||pos!=s->next_position) return -1;
    int d=s->c.dim,h=s->c.hidden,heads=s->c.heads,hs=d/heads;
    int kd=d*(int)s->c.kv_heads/heads,group=heads/(int)s->c.kv_heads;
    for(int i=0;i<d;i++) if(!isfinite(s->x[i])) return -1;
    if(s->neo&&first==0) {
        const int8_t *q=s->positions.q+(size_t)pos*d;float scale=s->positions.scale[pos];
        for(int i=0;i<d;i++)s->x[i]+=(float)q[i]*scale;
    }
    for(int n=first;n<end;n++) {
        const layer *l=&s->layer[n]; size_t off=(size_t)(n-(int)s->first)*s->c.context*kd;
        float *k=s->kc+off+(size_t)pos*kd,*v=s->vc+off+(size_t)pos*kd;
        norm(s,s->xb,s->x,l->na,l->ba,d);
        matmul(s,s->q,&l->q,s->xb); matmul(s,k,&l->k,s->xb); matmul(s,v,&l->v,s->xb);
        if(s->architecture==2) {
            for(int i=0;i<d;i+=hs)rms(s->q+i,s->q+i,l->qn,hs,s->epsilon);
            for(int i=0;i<kd;i+=hs)rms(k+i,k+i,l->kn,hs,s->epsilon);
        }
        if(!s->neo)for(int i=0;i<d;i+=2) {
            float angle=pos/powf(s->theta,(float)(i%hs)/hs),c=cosf(angle),sn=sinf(angle);
            float a=s->q[i],b=s->q[i+1]; s->q[i]=a*c-b*sn; s->q[i+1]=a*sn+b*c;
            if(i<kd) { a=k[i];b=k[i+1];k[i]=a*c-b*sn;k[i+1]=a*sn+b*c; }
        }
        int begin=s->neo&&(n&1)&&pos>=(int)s->window?pos-(int)s->window+1:0;
        for(int head=0;head<heads;head++) {
            float *att=s->att+(size_t)head*s->c.context; float mx=-INFINITY;
            for(int t=begin;t<=pos;t++) {
                const float *key=s->kc+off+(size_t)t*kd+(head/group)*hs;float score=0;
                for(int j=0;j<hs;j++) score+=s->q[head*hs+j]*key[j];
                att[t]=s->neo?score:score/sqrtf((float)hs); if(att[t]>mx) mx=att[t];
            }
            float sum=0;for(int t=begin;t<=pos;t++) { att[t]=expf(att[t]-mx);sum+=att[t]; }
            float *out=s->xb+head*hs;memset(out,0,(size_t)hs*4);
            for(int t=begin;t<=pos;t++) {
                const float *val=s->vc+off+(size_t)t*kd+(head/group)*hs;
                for(int j=0;j<hs;j++) out[j]+=(att[t]/sum)*val[j];
            }
        }
        matmul(s,s->xb2,&l->o,s->xb);for(int i=0;i<d;i++)s->x[i]+=s->xb2[i]+(s->neo?l->bo[i]:0);
        norm(s,s->xb,s->x,l->nf,l->bf,d);
        matmul(s,s->hb,&l->w1,s->xb);
        if(s->neo)for(int i=0;i<h;i++){
            float z=s->hb[i]+l->b1[i];s->hb[i]=0.5f*z*(1.0f+tanhf(0.7978845608f*(z+0.044715f*z*z*z)));
        } else {
            matmul(s,s->hb2,&l->w3,s->xb);
            for(int i=0;i<h;i++)s->hb[i]=(s->hb[i]/(1+expf(-s->hb[i])))*s->hb2[i];
        }
        matmul(s,s->xb,&l->w2,s->hb);for(int i=0;i<d;i++)s->x[i]+=s->xb[i]+(s->neo?l->b2[i]:0);
        YIELD();
    }
    s->next_position++;return 0;
}
float *ts_finish(ts_state *s) {
    if(s->role==2)return NULL;
    int64_t started=now_us();
    norm(s,s->xb,s->x,s->norm,s->norm_bias,s->c.dim);matmul(s,s->logits,&s->emb,s->xb);
    s->profile.finish_us+=now_us()-started;return s->logits;
}
int ts_argmax(ts_state *s) {
    int best=0;for(unsigned i=1;i<s->c.vocab;i++) if(s->logits[i]>s->logits[best]) best=(int)i;
    return best;
}
static int lookup(ts_state *s,const char *str) {
    token_index key={str,0};token_index *r=bsearch(&key,s->sorted,s->c.vocab,sizeof key,token_cmp);
    return r?r->id:-1;
}
int ts_encode(ts_state *s,const char *text,int *tokens,int cap) {
    if(s->spm)return sp_encode(s->spm,text,tokens,cap);
    if(s->role==2)return -1;
    if(s->bpe)return gpt2_encode(s->bpe,text,tokens,cap);
    if(!text||!tokens||cap<1) return -1;
    int n=0;tokens[n++]=1;
    if(*text) { int prefix=lookup(s," ");if(prefix<0||n>=cap)return -1;tokens[n++]=prefix; }
    for(const unsigned char *p=(const unsigned char*)text;*p;) {
        char piece[5]={0};int len=1;
        if((*p&0xe0)==0xc0)len=2;else if((*p&0xf0)==0xe0)len=3;else if((*p&0xf8)==0xf0)len=4;
        for(int j=1;j<len;j++) if(!p[j]||(p[j]&0xc0)!=0x80) {len=1;break;}
        memcpy(piece,p,(size_t)len);int id=lookup(s,piece);
        if(id>=0) {if(n>=cap)return -1;tokens[n++]=id;}
        else {for(int j=0;j<len;j++){if(n>=cap)return -1;tokens[n++]=(int)p[j]+3;}}
        p+=len;
    }
    for(;;) {
        float best=-INFINITY;int index=-1,id=-1;char joined[1025];
        for(int i=0;i<n-1;i++) {
            size_t a=strlen(s->tokens[tokens[i]]),b=strlen(s->tokens[tokens[i+1]]);
            if(a+b>512)continue;
            memcpy(joined,s->tokens[tokens[i]],a);memcpy(joined+a,s->tokens[tokens[i+1]],b+1);
            int candidate=lookup(s,joined);
            if(candidate>=0&&s->scores[candidate]>best) {best=s->scores[candidate];index=i;id=candidate;}
        }
        if(index<0)break;
        tokens[index]=id;memmove(tokens+index+1,tokens+index+2,(size_t)(n-index-2)*sizeof(int));n--;
    }
    return n;
}
const char *ts_decode(ts_state *s,int prev,int token) {
    if(token<0||(unsigned)token>=s->c.vocab)return "";
    if(s->spm){size_t n;const uint8_t *p=sp_piece(s->spm,token,&n);memcpy(s->decoded,p,n);s->decoded[n]=0;return s->decoded;}
    if(s->bpe){size_t n;const uint8_t *p=gpt2_piece(s->bpe,token,&n);memcpy(s->decoded,p,n);s->decoded[n]=0;return s->decoded;}
    if(s->role==2)return "";
    const char *p=s->tokens[token];if(prev==1&&*p==' ')p++;
    unsigned byte; if(strlen(p)==6&&sscanf(p,"<0x%2X>",&byte)==1&&byte<256)return s->byte_piece[byte];
    return p;
}
size_t ts_decode_length(ts_state *s,int prev,int token) {
    if(s->spm){size_t n;sp_piece(s->spm,token,&n);return n;}
    if(s->bpe){size_t n;gpt2_piece(s->bpe,token,&n);return n;}
    return strlen(ts_decode(s,prev,token));
}
const char *ts_decode_output(ts_state *s,int previous,int token,unsigned index,size_t *length){
    if(s->spm){int n=sp_decode(s->spm,token,index,s->decoded,512);if(n<0){*length=0;return "";}s->decoded[n]=0;*length=(size_t)n;return s->decoded;}
    const char *p=ts_decode(s,previous,token);*length=ts_decode_length(s,previous,token);return p;
}
