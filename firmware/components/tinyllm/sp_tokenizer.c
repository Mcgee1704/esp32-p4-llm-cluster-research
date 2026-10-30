/* Bounded BPE/Metaspace, matching pinned tokenizers0.22.1 normalization.
 * Independent C implementation; algorithm references and Unicode data notice
 * in THIRD_PARTY.md / UNICODE-LICENSE.txt. No regex or network runtime. */
#include "sp_tokenizer.h"
#include <stdlib.h>
#include <string.h>
#ifdef ESP_PLATFORM
#include "esp_heap_caps.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#define BUF(n) heap_caps_malloc((n),MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT)
#define PAUSE(i) do{if(((i)&2047u)==0)vTaskDelay(1);}while(0)
#define PAUSE_BPE(i) do{if(((i)&31u)==0)vTaskDelay(1);}while(0)
#else
#define BUF(n) malloc(n)
#define PAUSE(i) ((void)(i))
#define PAUSE_BPE(i) ((void)(i))
#endif
struct sp_tokenizer {
    const uint8_t *offsets,*strings,*merges,*added,*chars,*trie,*rewrites,*ranges;
    unsigned vocab,count,added_count,char_count,trie_count,rewrite_size,range_count,unk,eos;
};
static uint32_t u32(const uint8_t *p){uint32_t n;memcpy(&n,p,4);return n;}
static int utf8(const uint8_t *p,size_t n,unsigned *code){
    if(!n)return -1;
    unsigned c=p[0];int w;
    if(c<128){*code=c;return 1;}
    if(c>=0xc2&&c<=0xdf){w=2;c&=31;}else if(c>=0xe0&&c<=0xef){w=3;c&=15;}else if(c>=0xf0&&c<=0xf4){w=4;c&=7;}else return -1;
    if(n<(size_t)w)return -1;
    for(int i=1;i<w;i++){if((p[i]&0xc0)!=0x80)return -1;c=(c<<6)|(p[i]&63);}
    if((w==2&&c<128)||(w==3&&c<2048)||(w==4&&c<65536)||c>0x10ffff||(c>=0xd800&&c<=0xdfff))return -1;
    *code=c;return w;
}
static int valid(const uint8_t *p,size_t n){while(n){unsigned c;int w=utf8(p,n,&c);if(w<0)return 0;p+=w;n-=w;}return 1;}
const uint8_t *sp_piece(const sp_tokenizer *t,int id,size_t *n){
    *n=0;if(!t||id<0||(unsigned)id>=t->vocab)return NULL;
    unsigned a=u32(t->offsets+4*(unsigned)id),b=u32(t->offsets+4*((unsigned)id+1));*n=b-a;return t->strings+a;
}
static unsigned dart_offset(unsigned v){return (v>>10)<<((v&512)>>6);}
sp_tokenizer *sp_open(const void *blob,size_t bytes,unsigned vocab,unsigned eos){
    const uint8_t *b=blob;if(!b||bytes<64||memcmp(b,"SPBP0001",8)||u32(b+8)!=vocab||vocab<259||vocab>65536||u32(b+44)!=eos||eos>=vocab)return NULL;
    unsigned merges=u32(b+12),strings=u32(b+16),added=u32(b+20),norm=u32(b+24),ranges=u32(b+28),chars=u32(b+32);
    if(merges>100000||!strings||strings>4*1024*1024||!added||added>64||norm<1029||norm>1024*1024||!ranges||ranges>10000||!chars||chars>vocab||u32(b+36)!=1||u32(b+40)>=vocab)return NULL;
    for(int i=48;i<64;i++)if(b[i])return NULL;
    size_t pos=64+((size_t)vocab+1)*4;if(pos>bytes||strings>bytes-pos)return NULL;
    size_t string_start=pos;pos=(pos+strings+3)&~(size_t)3;
    size_t merges_start=pos;pos+=(size_t)merges*16;size_t added_start=pos;pos+=(size_t)added*8;
    size_t chars_start=pos;pos+=(size_t)chars*8;size_t norm_start=pos;pos+=norm;size_t norm_end=pos;pos=(pos+3)&~(size_t)3;
    if(pos>bytes||(size_t)ranges*12!=bytes-pos)return NULL;
    for(size_t i=string_start+strings;i<merges_start;i++)if(b[i])return NULL;
    for(size_t i=norm_end;i<pos;i++)if(b[i])return NULL;
    unsigned trie_bytes=u32(b+norm_start);if(trie_bytes<1024||(trie_bytes&1023)||trie_bytes>=norm-4)return NULL;
    sp_tokenizer *t=calloc(1,sizeof *t);if(!t)return NULL;
    t->vocab=vocab;t->count=merges;t->added_count=added;t->char_count=chars;t->unk=u32(b+40);t->eos=eos;t->range_count=ranges;
    t->offsets=b+64;t->strings=b+string_start;t->merges=b+merges_start;t->added=b+added_start;t->chars=b+chars_start;
    t->trie=b+norm_start+4;t->trie_count=trie_bytes/4;t->rewrites=t->trie+trie_bytes;t->rewrite_size=norm-4-trie_bytes;t->ranges=b+pos;
    if(u32(t->offsets)||u32(t->offsets+4*(size_t)vocab)!=strings)goto bad;
    for(unsigned i=0;i<vocab;i++){
        unsigned a=u32(t->offsets+4*i),end=u32(t->offsets+4*(i+1));if(end<=a||end>strings||end-a>512||memchr(t->strings+a,0,end-a)||!valid(t->strings+a,end-a))goto bad;PAUSE(i);
    }
    uint8_t *seen=calloc(merges?merges:1,1);if(!seen)goto bad;
    unsigned last_a=0,last_b=0;
    for(unsigned i=0;i<merges;i++){
        const uint8_t *r=t->merges+16*(size_t)i;unsigned a=u32(r),bb=u32(r+4),rank=u32(r+8),id=u32(r+12);size_t na,nb,no;
        if(a>=vocab||bb>=vocab||id>=vocab||rank>=merges||seen[rank]||(i&&(a<last_a||(a==last_a&&bb<=last_b)))){free(seen);goto bad;}
        const uint8_t *pa=sp_piece(t,(int)a,&na),*pb=sp_piece(t,(int)bb,&nb),*po=sp_piece(t,(int)id,&no);
        if(na+nb!=no||memcmp(pa,po,na)||memcmp(pb,po+na,nb)){free(seen);goto bad;}seen[rank]=1;last_a=a;last_b=bb;PAUSE(i);
    }free(seen);
    int found_eos=0;
    for(unsigned i=0;i<added;i++){
        unsigned id=u32(t->added+8*i),flags=u32(t->added+8*i+4);if(id>=vocab||flags>3)goto bad;if(id==eos)found_eos=1;
        for(unsigned j=0;j<i;j++)if(u32(t->added+8*j)==id)goto bad;
    }if(!found_eos)goto bad;
    unsigned last=0;
    for(unsigned i=0;i<chars;i++){
        unsigned cp=u32(t->chars+8*i),id=u32(t->chars+8*i+4),actual;size_t n;const uint8_t *p=sp_piece(t,(int)id,&n);
        if(!p||(i&&cp<=last)||utf8(p,n,&actual)!=(int)n||cp!=actual)goto bad;
        last=cp;
    }
    if(t->rewrites[t->rewrite_size-1]||!valid(t->rewrites,t->rewrite_size))goto bad;
    unsigned root=u32(t->trie);if((root&0x800001ff)||dart_offset(root)>=t->trie_count)goto bad;
    for(unsigned i=0;i<t->trie_count;i++){
        unsigned v=u32(t->trie+4*i);if(v&0x80000000u)continue;
        unsigned off=dart_offset(v),child=i^off;if(child>=t->trie_count)goto bad;
        if(v&256){unsigned leaf=u32(t->trie+4*child),value=leaf&0x7fffffffu;
            if(!(leaf&0x80000000u)||value>=t->rewrite_size||(t->rewrites[value]&0xc0)==0x80||!memchr(t->rewrites+value,0,t->rewrite_size-value))goto bad;}
        PAUSE(i);
    }
    last=0;
    for(unsigned i=0;i<ranges;i++){
        const uint8_t *r=t->ranges+12*i;unsigned lo=u32(r),hi=u32(r+4),flags=u32(r+8);
        if(lo>hi||hi>0x10ffff||!flags||flags>255||(flags&31)>15||(i&&lo<=last))goto bad;
        last=hi;
    }
    return t;
bad:free(t);return NULL;
}
void sp_close(sp_tokenizer *t){free(t);}
static unsigned properties(const sp_tokenizer *t,unsigned cp){
    unsigned lo=0,hi=t->range_count;while(lo<hi){unsigned m=lo+(hi-lo)/2;const uint8_t *p=t->ranges+12*m;
        if(cp<u32(p))hi=m;else if(cp>u32(p+4))lo=m+1;else return u32(p+8);}return 0;
}
/* Forward extended-grapheme state for Unicode16 GB3..GB13. Property data are
 * exported from unicode-segmentation1.12.0; no locale-dependent classification. */
static size_t grapheme_end(const sp_tokenizer *t,const uint8_t *s,size_t n){
    unsigned cp;int w=utf8(s,n,&cp);if(w<0)return 0;size_t at=(size_t)w;unsigned f=properties(t,cp),prev=f&31;
    int ri=prev==11,ep=prev==4,zwj_ep=0,cons=prev==5,link=0;
    while(at<n){w=utf8(s+at,n-at,&cp);if(w<0)return 0;f=properties(t,cp);unsigned after=f&31;int join=0;
        if(prev==1&&after==7)join=1;
        else if(prev==1||prev==2||prev==7||after==1||after==2||after==7)join=0;
        else if(prev==6&&(after==6||after==14||after==8||after==9))join=1;
        else if((prev==8||prev==14)&&(after==14||after==13))join=1;
        else if((prev==9||prev==13)&&after==13)join=1;
        else if(after==3||after==15||after==12||prev==10)join=1;
        else if(after==5&&cons&&link)join=1;
        else if(prev==15&&after==4&&zwj_ep)join=1;
        else if(prev==11&&after==11&&(ri&1))join=1;
        if(!join)break;
        if(after==15){zwj_ep=ep;ep=0;}else{zwj_ep=0;if(after==4)ep=1;else if(after!=3)ep=0;}
        if(after==5){cons=1;link=0;}else if(f&64){if(cons)link=1;}else if(!(f&32)){cons=0;link=0;}
        ri=after==11?ri+1:0;prev=after;at+=(size_t)w;
    }return at;
}
static const uint8_t *transform(const sp_tokenizer *t,const uint8_t *p,size_t n,size_t *length){
    unsigned node=dart_offset(u32(t->trie));
    for(size_t i=0;i<n&&p[i];i++){
        node^=p[i];if(node>=t->trie_count)return NULL;unsigned v=u32(t->trie+4*node);if((v&0x800000ffu)!=p[i])return NULL;
        node^=dart_offset(v);if(node>=t->trie_count)return NULL;
        if(v&256){unsigned off=u32(t->trie+4*node)&0x7fffffffu;if(off>=t->rewrite_size)return NULL;
            const uint8_t *out=t->rewrites+off;*length=strlen((const char*)out);return out;}
    }return NULL;
}
static int normalize_span(const sp_tokenizer *t,const uint8_t *text,size_t n,uint8_t *out,size_t cap){
    uint8_t *tmp=BUF(cap?cap:1);if(!tmp)return -1;size_t at=0,used=0,last_nonwhite=0;
    while(at<n){size_t g=grapheme_end(t,text+at,n-at);if(!g)goto bad;size_t len=0;const uint8_t *p=g<6?transform(t,text+at,g,&len):NULL;
        if(p){if(len>cap-used)goto bad;memcpy(tmp+used,p,len);used+=len;}
        else for(size_t j=0;j<g;){unsigned cp;int w=utf8(text+at+j,g-j,&cp);if(w<0)goto bad;
            p=transform(t,text+at+j,(size_t)w,&len);if(!p){p=text+at+j;len=(size_t)w;}
            if(len>cap-used)goto bad;
            memcpy(tmp+used,p,len);used+=len;j+=(size_t)w;}
        at+=g;PAUSE(at);
    }
    for(size_t j=0;j<used;){unsigned cp;int w=utf8(tmp+j,used-j,&cp);if(w<0)goto bad;j+=(size_t)w;if(!(properties(t,cp)&128))last_nonwhite=j;}
    used=0;
    for(size_t j=0;j<last_nonwhite;){size_t end=j;while(end<last_nonwhite&&tmp[end]==' ')end++;
        if(end-j>=2){if(cap-used<3)goto bad;memcpy(out+used,"\xe2\x96\x81",3);used+=3;j=end;}
        else {if(used>=cap)goto bad;out[used++]=tmp[j++];}}
    free(tmp);return (int)used;
bad:free(tmp);return -1;
}
int sp_normalize(const sp_tokenizer *t,const char *text,void *out,size_t cap){
    if(!t||!text||!out||!cap)return -1;
    size_t n=strlen(text);if(n>4096||!valid((const uint8_t*)text,n))return -1;
    return normalize_span(t,(const uint8_t*)text,n,out,cap);
}
static int char_id(const sp_tokenizer *t,unsigned cp){
    unsigned lo=0,hi=t->char_count;while(lo<hi){unsigned m=lo+(hi-lo)/2,c=u32(t->chars+8*m);if(cp<c)hi=m;else if(cp>c)lo=m+1;else return (int)u32(t->chars+8*m+4);}return (int)t->unk;
}
static int merge(const sp_tokenizer *t,int a,int b,int *id){
    unsigned lo=0,hi=t->count;while(lo<hi){unsigned m=lo+(hi-lo)/2;const uint8_t *r=t->merges+16*(size_t)m;unsigned x=u32(r),y=u32(r+4);
        if((unsigned)a<x||((unsigned)a==x&&(unsigned)b<y))hi=m;else if((unsigned)a>x||((unsigned)a==x&&(unsigned)b>y))lo=m+1;
        else{*id=(int)u32(r+12);return (int)u32(r+8);}}return -1;
}
static int flush(const sp_tokenizer *t,int *scratch,int n,int *out,int cap){
    unsigned rounds=0;
    for(;;){int best=-1,rank=0x7fffffff,result=-1;
        for(int i=0;i<n-1;i++){int id,r=merge(t,scratch[i],scratch[i+1],&id);if(r>=0&&r<rank){rank=r;best=i;result=id;}}
        if(best<0)break;
        scratch[best]=result;memmove(scratch+best+1,scratch+best+2,(size_t)(n-best-2)*4);n--;PAUSE_BPE(++rounds);
    }if(n>cap)return -1;memcpy(out,scratch,(size_t)n*4);return n;
}
static int encode_part(const sp_tokenizer *t,const uint8_t *p,size_t n,int first,int *scratch,int *out,int cap){
    int count=0,total=0;unsigned cp=0;int marker=char_id(t,0x2581);
    if(n&&first){if(utf8(p,n,&cp)<0)return -1;if(cp!=32&&cp!=0x2581)scratch[count++]=marker;}
    for(size_t i=0;i<n;){int w=utf8(p+i,n-i,&cp);if(w<0)return -1;i+=(size_t)w;int id=char_id(t,cp==32?0x2581:cp);
        if(cp==32||cp==0x2581){if(count){int k=flush(t,scratch,count,out+total,cap-total);if(k<0)return -1;total+=k;count=0;}}
        if(!(id==(int)t->unk&&count&&scratch[count-1]==id))scratch[count++]=id;
    }
    if(count){int k=flush(t,scratch,count,out+total,cap-total);if(k<0)return -1;total+=k;}return total;
}
static size_t added_match(const sp_tokenizer *t,const uint8_t *p,size_t n,int normalized,unsigned *id,size_t *len){
    size_t best=n;*len=0;
    for(unsigned i=0;i<t->added_count;i++){
        const uint8_t *r=t->added+8*i;if((int)(u32(r+4)&1)!=normalized)continue;size_t z;unsigned token=u32(r);const uint8_t *s=sp_piece(t,(int)token,&z);
        for(size_t j=0;j+z<=n;j++)if(!memcmp(p+j,s,z)){if(j<best||(j==best&&z>*len)){best=j;*id=token;*len=z;}break;}
    }return best;
}
int sp_encode(const sp_tokenizer *t,const char *text,int *out,int cap){
    if(!t||!text||!out||cap<1)return -1;
    size_t n=strlen(text);if(n>4096||!valid((const uint8_t*)text,n))return -1;if(!n)return 0;
    size_t bound=n*32+16;if(bound>65536)bound=65536;uint8_t *norm=BUF(bound);int *scratch=BUF((bound+1)*4);
    if(!norm||!scratch){free(norm);free(scratch);return -1;}
    size_t at=0;int total=0;
    while(at<n){unsigned id=0;size_t len=0,part=added_match(t,(const uint8_t*)text+at,n-at,0,&id,&len);
        if(part){int size=normalize_span(t,(const uint8_t*)text+at,part,norm,bound);if(size<0)goto bad;size_t j=0;
            while(j<(size_t)size){unsigned rid=0;size_t rlen=0,next=added_match(t,norm+j,(size_t)size-j,1,&rid,&rlen);
                if(next){int k=encode_part(t,norm+j,next,at==0&&j==0,scratch,out+total,cap-total);if(k<0)goto bad;total+=k;j+=next;}
                if(rlen){if(total>=cap)goto bad;out[total++]=(int)rid;j+=rlen;}
            }at+=part;
        }
        if(len){if(total>=cap)goto bad;out[total++]=(int)id;at+=len;}
    }free(norm);free(scratch);return total;
bad:free(norm);free(scratch);return -1;
}
int sp_decode(const sp_tokenizer *t,int token,unsigned index,void *out,size_t cap){
    size_t n;const uint8_t *p=sp_piece(t,token,&n);if(!p||!out)return -1;uint8_t *b=out;size_t used=0;
    for(size_t i=0;i<n;){if(n-i>=3&&!memcmp(p+i,"\xe2\x96\x81",3)){i+=3;if(!index)continue;if(used>=cap)return -1;b[used++]=' ';}
        else {if(used>=cap)return -1;b[used++]=p[i++];}}
    return (int)used;
}
