/* Bounded GPT-2 byte BPE. Byte-level classes are exported from the pinned
 * tokenizer backend. No locale/regex runtime or external assets are required. */
#include "gpt2_tokenizer.h"
#include <stdlib.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define PAUSE(i) do {if(((i)&2047u)==0)vTaskDelay(1);}while(0)
#else
#define PAUSE(i) ((void)(i))
#endif
struct gpt2_tokenizer {
    const uint8_t *offsets,*strings,*merges,*ranges;
    unsigned vocab,count,range_count,eos,special_count,digits;const uint8_t *specials;int bytes[256];
};
static uint32_t u32(const uint8_t *p){uint32_t n;memcpy(&n,p,4);return n;}
const uint8_t *gpt2_piece(const gpt2_tokenizer *t,int token,size_t *length) {
    *length=0;if(!t||token<0||(unsigned)token>=t->vocab)return NULL;
    unsigned a=u32(t->offsets+4*(unsigned)token),b=u32(t->offsets+4*((unsigned)token+1));
    *length=b-a;return t->strings+a;
}
static int is_special(const gpt2_tokenizer *t,unsigned id){if(!t->specials)return id==t->eos;for(unsigned i=0;i<t->special_count;i++)if(u32(t->specials+4*i)==id)return 1;return 0;}
gpt2_tokenizer *gpt2_open(const uint8_t *b,size_t bytes,unsigned vocab,unsigned eos) {
    if(!b||bytes<24)return NULL;
    int v2=!memcmp(b,"G2BP0002",8);
    if((!v2&&memcmp(b,"G2BP0001",8))||u32(b+8)!=vocab||vocab<259||vocab>65536||eos>=vocab)return NULL;
    unsigned count=u32(b+12),strings=u32(b+16),ranges=u32(b+20);
    if(count>100000||strings>4*1024*1024||ranges>5000)return NULL;
    unsigned flags=0,special_count=0;size_t header=24;
    if(v2){if(bytes<32)return NULL;flags=u32(b+24);special_count=u32(b+28);if(flags>1||!special_count||special_count>64)return NULL;header=32+(size_t)special_count*4;}
    size_t start=header+((size_t)vocab+1)*4;if(start>bytes||strings>bytes-start)return NULL;
    size_t merge_start=(start+strings+3)&~(size_t)3;
    if(merge_start>bytes||(size_t)count*16+(size_t)ranges*12!=bytes-merge_start)return NULL;
    gpt2_tokenizer *t=calloc(1,sizeof *t);if(!t)return NULL;
    t->vocab=vocab;t->count=count;t->range_count=ranges;t->eos=eos;
    t->digits=flags;t->special_count=special_count;t->specials=v2?b+32:NULL;
    t->offsets=b+header;t->strings=b+start;t->merges=b+merge_start;t->ranges=t->merges+(size_t)count*16;
    for(int i=0;i<256;i++)t->bytes[i]=-1;
    if(u32(t->offsets)||u32(t->offsets+(size_t)vocab*4)!=strings)goto bad;
    for(unsigned i=0;i<vocab;i++) {
        unsigned a=u32(t->offsets+4*i),end=u32(t->offsets+4*(i+1));
        if(end<=a||end>strings||end-a>512)goto bad;
        if(end-a==1){unsigned c=t->strings[a];if(t->bytes[c]>=0)goto bad;t->bytes[c]=(int)i;}
        PAUSE(i);
    }
    for(int i=0;i<256;i++)if(t->bytes[i]<0)goto bad;
    size_t special_len;const uint8_t *special=gpt2_piece(t,(int)eos,&special_len);
    if(!v2&&(special_len!=13||memcmp(special,"<|endoftext|>",13)))goto bad;
    if(v2){if(!is_special(t,eos))goto bad;for(unsigned i=0;i<special_count;i++){
        unsigned id=u32(t->specials+4*i);if(id>=vocab)goto bad;
        size_t n;const uint8_t *p=gpt2_piece(t,(int)id,&n);if(!n||memchr(p,0,n))goto bad;
        for(unsigned j=0;j<i;j++){size_t m;unsigned prev=u32(t->specials+4*j);const uint8_t *q=gpt2_piece(t,(int)prev,&m);if(id==prev||(n==m&&!memcmp(p,q,n)))goto bad;}
    }}
    uint8_t *seen=calloc(count?count:1,1);if(!seen)goto bad;
    unsigned last_a=0,last_b=0;
    for(unsigned i=0;i<count;i++) {
        const uint8_t *r=t->merges+(size_t)i*16;
        unsigned a=u32(r),bb=u32(r+4),rank=u32(r+8),out=u32(r+12);
        if(a>=vocab||bb>=vocab||out>=vocab||is_special(t,a)||is_special(t,bb)||is_special(t,out)||rank>=count||seen[rank]||
           (i&&(a<last_a||(a==last_a&&bb<=last_b)))){free(seen);goto bad;}
        seen[rank]=1;last_a=a;last_b=bb;
        size_t na,nb,no;const uint8_t *pa=gpt2_piece(t,(int)a,&na),*pb=gpt2_piece(t,(int)bb,&nb),*po=gpt2_piece(t,(int)out,&no);
        if(na+nb!=no||memcmp(pa,po,na)||memcmp(pb,po+na,nb)){free(seen);goto bad;}
        PAUSE(i);
    }
    free(seen);
    unsigned previous=0;
    for(unsigned i=0;i<ranges;i++) {
        const uint8_t *r=t->ranges+(size_t)i*12;unsigned lo=u32(r),hi=u32(r+4),kind=u32(r+8);
        if(lo>hi||hi>0x10ffff||!kind||kind>3||(i&&lo<=previous))goto bad;
        previous=hi;
    }
    return t;
bad:free(t);return NULL;
}
void gpt2_close(gpt2_tokenizer *t){free(t);}
static int category(const gpt2_tokenizer *t,unsigned code) {
    unsigned lo=0,hi=t->range_count;
    while(lo<hi){unsigned mid=lo+(hi-lo)/2;const uint8_t *r=t->ranges+(size_t)mid*12;
        if(code<u32(r))hi=mid;else if(code>u32(r+4))lo=mid+1;else return (int)u32(r+8);}
    return 0;
}
static int utf8(const uint8_t *p,const uint8_t *end,unsigned *code) {
    if(p>=end)return -1;
    unsigned c=*p;int n;
    if(c<128){*code=c;return 1;}
    if(c>=0xc2&&c<=0xdf){n=2;c&=31;}
    else if(c>=0xe0&&c<=0xef){n=3;c&=15;}
    else if(c>=0xf0&&c<=0xf4){n=4;c&=7;}else return -1;
    if(end-p<n)return -1;
    for(int i=1;i<n;i++){if((p[i]&0xc0)!=0x80)return -1;c=(c<<6)|(p[i]&63);}
    if((n==2&&c<128)||(n==3&&c<2048)||(n==4&&c<65536)||c>0x10ffff||(c>=0xd800&&c<=0xdfff))return -1;
    *code=c;return n;
}
static int merge_rank(const gpt2_tokenizer *t,unsigned a,unsigned b,int *out) {
    unsigned lo=0,hi=t->count;
    while(lo<hi){unsigned mid=lo+(hi-lo)/2;const uint8_t *r=t->merges+(size_t)mid*16;unsigned ra=u32(r),rb=u32(r+4);
        if(a<ra||(a==ra&&b<rb))hi=mid;else if(a>ra||(a==ra&&b>rb))lo=mid+1;
        else {*out=(int)u32(r+12);return (int)u32(r+8);}}
    return -1;
}
static int bpe(const gpt2_tokenizer *t,const uint8_t *p,size_t length,int *scratch,int *tokens,int cap) {
    int n=(int)length;for(int i=0;i<n;i++)scratch[i]=t->bytes[p[i]];
    for(;;){int best=-1,rank=0x7fffffff,result=-1;
        for(int i=0;i<n-1;i++){int out,r=merge_rank(t,(unsigned)scratch[i],(unsigned)scratch[i+1],&out);
            if(r>=0&&r<rank){rank=r;best=i;result=out;}}
        if(best<0)break;
        scratch[best]=result;memmove(scratch+best+1,scratch+best+2,(size_t)(n-best-2)*sizeof(int));n--;
    }
    if(n>cap)return -1;
    memcpy(tokens,scratch,(size_t)n*sizeof(int));return n;
}
static const uint8_t *piece_end(const gpt2_tokenizer *t,const uint8_t *p,const uint8_t *end) {
    static const char *contractions[]={"'s","'t","'re","'ve","'m","'ll","'d"};
    if(*p=='\'')for(unsigned i=0;i<7;i++){size_t n=strlen(contractions[i]);if((size_t)(end-p)>=n&&!memcmp(p,contractions[i],n))return p+n;}
    unsigned code;int n=utf8(p,end,&code);if(n<0)return NULL;
    const uint8_t *q=p;int kind=category(t,code);
    if(code==32&&p+1<end){unsigned next;int m=utf8(p+1,end,&next);if(m<0)return NULL;
        if(category(t,next)!=3){q=p+1;kind=category(t,next);}}
    if(kind==3){const uint8_t *last=q;
        while(q<end){n=utf8(q,end,&code);if(n<0)return NULL;if(category(t,code)!=3)break;last=q;q+=n;}
        /* Greedy whitespace with (?!\S): retain the last character for the
         * next match when there are at least two before a non-space. */
        return q<end&&last>p?last:q;
    }
    while(q<end){n=utf8(q,end,&code);if(n<0)return NULL;if(category(t,code)!=kind)break;q+=n;}
    return q;
}
int gpt2_encode(const gpt2_tokenizer *t,const char *text,int *tokens,int cap) {
    if(!t||!text||!tokens||cap<1)return -1;
    size_t length=strlen(text);if(length>4096)return -1;
    if(!length)return 0;
    int *scratch=malloc(length*sizeof(int));if(!scratch)return -1;
    const uint8_t *p=(const uint8_t*)text,*end=p+length;int total=0;
    while(p<end) {
        const uint8_t *boundary=end;unsigned matched=t->eos;size_t matched_length=0;
        unsigned count=t->specials?t->special_count:1;
        for(unsigned i=0;i<count;i++) {
            unsigned id=t->specials?u32(t->specials+4*i):t->eos;size_t n;const uint8_t *sp=gpt2_piece(t,(int)id,&n);
            for(const uint8_t *q=p;(size_t)(end-q)>=n;q++)if(!memcmp(q,sp,n)){
                if(q<boundary||(q==boundary&&n>matched_length)){boundary=q;matched=id;matched_length=n;}break;
            }
        }
        if(boundary==p){if(total>=cap)goto bad;tokens[total++]=(int)matched;p+=matched_length;continue;}
        /* Digits runs before ByteLevel, so a following digit terminates the
         * current segment even for ByteLevel trailing-whitespace lookahead. */
        if(t->digits)for(const uint8_t *scan=p;scan<boundary;) {
            unsigned code;int width=utf8(scan,boundary,&code);if(width<0)goto bad;
            if(category(t,code)==2){boundary=scan==p?p+width:scan;break;}scan+=width;
        }
        const uint8_t *q=piece_end(t,p,boundary);if(!q||q<=p)goto bad;
        int n=bpe(t,p,(size_t)(q-p),scratch,tokens+total,cap-total);if(n<0)goto bad;
        total+=n;p=q;
    }
    free(scratch);return total;
bad:free(scratch);return -1;
}
