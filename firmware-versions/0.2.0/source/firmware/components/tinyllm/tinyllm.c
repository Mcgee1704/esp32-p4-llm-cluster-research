/* Portable scalar Llama inference. Algorithm reference: karpathy/llama2.c (MIT).
 * New P4LM parser, per-row INT8 layout and layer-range API; see THIRD_PARTY.md. */
#include "tinyllm.h"
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdio.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define ALLOC(n) heap_caps_calloc(1,(n),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)
#define YIELD() vTaskDelay(1)
#else
#define ALLOC(n) calloc(1,(n))
#define YIELD() ((void)0)
#endif
typedef struct { const float *scale; const int8_t *q; int rows,cols; } matrix;
typedef struct { const float *na,*nf; matrix q,k,v,o,w1,w2,w3; } layer;
typedef struct { const char *text; int id; } token_index;
struct ts_state {
    ts_config c; const uint8_t *blob; matrix emb; layer layer[32]; const float *norm;
    float *x,*xb,*xb2,*hb,*hb2,*q,*att,*logits,*kc,*vc;
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
static int read_matrix(matrix *m,const uint8_t **p,const uint8_t *end,int r,int c) {
    m->rows=r; m->cols=c;
    m->scale=take(p,end,(size_t)r*4); if(!m->scale) return -1;
    for(int i=0;i<r;i++) if(!isfinite(m->scale[i])||m->scale[i]<=0) return -1;
    m->q=take(p,end,(size_t)r*c); return m->q?0:-1;
}
static int token_cmp(const void *a,const void *b) {
    return strcmp(((const token_index*)a)->text,((const token_index*)b)->text);
}
ts_state *ts_open(const void *blob,size_t bytes) {
    const uint8_t *b=blob;
    if(!b||((uintptr_t)b&3)||bytes<128||memcmp(b,"P4LM0001",8)) return NULL;
    ts_config c; memcpy(&c,b+8,sizeof c);
    if(!c.dim||c.dim>1024||c.dim%4||!c.hidden||c.hidden>4096||c.hidden%4||
       !c.layers||c.layers>32||!c.heads||c.heads>c.dim||!c.kv_heads||c.kv_heads>c.heads||
       c.heads%c.kv_heads||c.dim%c.heads||(c.dim/c.heads)%2||
       c.vocab<259||c.vocab>65536||!c.context||c.context>1024) return NULL;
    size_t weights=u32(b+36),toksize=u32(b+40);
    if(weights>bytes-128||toksize!=bytes-128-weights||weights%4||
       ts_crc32(b+128,bytes-128)!=u32(b+80)) return NULL;
    ts_state *s=calloc(1,sizeof *s); if(!s) return NULL;
    s->c=c; s->blob=b;
    const uint8_t *p=b+128,*end=p+weights;
    int d=(int)c.dim,h=(int)c.hidden,kd=d*(int)c.kv_heads/(int)c.heads;
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
    for(unsigned i=1;i<c.vocab;i++) if(!strcmp(s->sorted[i-1].text,s->sorted[i].text)) goto fail;
    for(int i=0;i<256;i++) s->byte_piece[i][0]=(char)i;
    s->x=ALLOC(c.dim*4); s->xb=ALLOC(c.dim*4); s->xb2=ALLOC(c.dim*4);
    s->hb=ALLOC(c.hidden*4); s->hb2=ALLOC(c.hidden*4); s->q=ALLOC(c.dim*4);
    s->att=ALLOC(c.heads*c.context*4); s->logits=ALLOC(c.vocab*4);
    size_t cache=(size_t)c.layers*c.context*(unsigned)kd*4;
    s->kc=ALLOC(cache); s->vc=ALLOC(cache);
    if(!s->x||!s->xb||!s->xb2||!s->hb||!s->hb2||!s->q||!s->att||!s->logits||!s->kc||!s->vc) goto fail;
    return s;
fail: ts_close(s); return NULL;
}
void ts_close(ts_state *s) {
    if(!s) return;
    free(s->x);free(s->xb);free(s->xb2);free(s->hb);free(s->hb2);free(s->q);
    free(s->att);free(s->logits);free(s->kc);free(s->vc);free(s->tokens);
    free(s->scores);free(s->sorted);free(s->strings);free(s);
}
const ts_config *ts_config_get(const ts_state *s) { return &s->c; }
const uint8_t *ts_model_id(const ts_state *s) { return s->blob+48; }
void ts_reset(ts_state *s) {
    s->next_position=0;
    /* Stale cache is never read: all positions through the current one are overwritten. */
    memset(s->x,0,s->c.dim*4);
}
float *ts_x(ts_state *s) { return s->x; }
static void rms(float *out,const float *x,const float *w,int n) {
    float sum=0; for(int i=0;i<n;i++) sum+=x[i]*x[i];
    float inv=1.0f/sqrtf(sum/n+1e-5f);
    for(int i=0;i<n;i++) out[i]=w[i]*(x[i]*inv);
}
static void matmul(float *out,const matrix *m,const float *x) {
    for(int i=0;i<m->rows;i++) {
        float sum=0; const int8_t *q=m->q+(size_t)i*m->cols;
        for(int j=0;j<m->cols;j++) sum+=(float)q[j]*x[j];
        out[i]=sum*m->scale[i];
        if((i&255)==255) YIELD();
    }
}
int ts_embed(ts_state *s,int token) {
    if(token<0||(unsigned)token>=s->c.vocab) return -1;
    const int8_t *q=s->emb.q+(size_t)token*s->c.dim;
    for(unsigned j=0;j<s->c.dim;j++) s->x[j]=q[j]*s->emb.scale[token];
    return 0;
}
int ts_layers(ts_state *s,int first,int end,int pos) {
    if(first<0||end<=first||(unsigned)end>s->c.layers||pos<0||
       (unsigned)pos>=s->c.context||pos!=s->next_position) return -1;
    int d=s->c.dim,h=s->c.hidden,heads=s->c.heads,hs=d/heads;
    int kd=d*(int)s->c.kv_heads/heads,group=heads/(int)s->c.kv_heads;
    for(int i=0;i<d;i++) if(!isfinite(s->x[i])) return -1;
    for(int n=first;n<end;n++) {
        const layer *l=&s->layer[n]; size_t off=(size_t)n*s->c.context*kd;
        float *k=s->kc+off+(size_t)pos*kd,*v=s->vc+off+(size_t)pos*kd;
        rms(s->xb,s->x,l->na,d);
        matmul(s->q,&l->q,s->xb); matmul(k,&l->k,s->xb); matmul(v,&l->v,s->xb);
        for(int i=0;i<d;i+=2) {
            float angle=pos/powf(10000.0f,(float)(i%hs)/hs),c=cosf(angle),sn=sinf(angle);
            float a=s->q[i],b=s->q[i+1]; s->q[i]=a*c-b*sn; s->q[i+1]=a*sn+b*c;
            if(i<kd) { a=k[i];b=k[i+1];k[i]=a*c-b*sn;k[i+1]=a*sn+b*c; }
        }
        for(int head=0;head<heads;head++) {
            float *att=s->att+(size_t)head*s->c.context; float mx=-INFINITY;
            for(int t=0;t<=pos;t++) {
                const float *key=s->kc+off+(size_t)t*kd+(head/group)*hs;float score=0;
                for(int j=0;j<hs;j++) score+=s->q[head*hs+j]*key[j];
                att[t]=score/sqrtf((float)hs); if(att[t]>mx) mx=att[t];
            }
            float sum=0;for(int t=0;t<=pos;t++) { att[t]=expf(att[t]-mx);sum+=att[t]; }
            float *out=s->xb+head*hs;memset(out,0,(size_t)hs*4);
            for(int t=0;t<=pos;t++) {
                const float *val=s->vc+off+(size_t)t*kd+(head/group)*hs;
                for(int j=0;j<hs;j++) out[j]+=(att[t]/sum)*val[j];
            }
        }
        matmul(s->xb2,&l->o,s->xb);for(int i=0;i<d;i++) s->x[i]+=s->xb2[i];
        rms(s->xb,s->x,l->nf,d);
        matmul(s->hb,&l->w1,s->xb);matmul(s->hb2,&l->w3,s->xb);
        for(int i=0;i<h;i++) s->hb[i]=(s->hb[i]/(1+expf(-s->hb[i])))*s->hb2[i];
        matmul(s->xb,&l->w2,s->hb);for(int i=0;i<d;i++) s->x[i]+=s->xb[i];
        YIELD();
    }
    s->next_position++;return 0;
}
float *ts_finish(ts_state *s) {
    rms(s->xb,s->x,s->norm,s->c.dim);matmul(s->logits,&s->emb,s->xb);return s->logits;
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
    const char *p=s->tokens[token];if(prev==1&&*p==' ')p++;
    unsigned byte; if(strlen(p)==6&&sscanf(p,"<0x%2X>",&byte)==1&&byte<256)return s->byte_piece[byte];
    return p;
}
