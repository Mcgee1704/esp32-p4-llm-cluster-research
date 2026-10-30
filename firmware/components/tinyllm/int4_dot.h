#pragma once
#include <stdint.h>

/* Even column counts are guaranteed by the admitted model format. Decode one
 * packed byte per row for two columns, preserving the scalar FP32 add order.
 * No FMA, horizontal reduction, LUT, model-format or quantizer change. */
static inline void ts_int4_dot4(float out[4],const uint8_t *q0,const uint8_t *q1,
                                const uint8_t *q2,const uint8_t *q3,
                                const float *x,int cols) {
    float a=0,b=0,c=0,d=0;
    for(int j=0;j<cols;j+=2) {
        unsigned u=q0[j/2],v=q1[j/2],w=q2[j/2],z=q3[j/2];
        float x0=x[j],x1=x[j+1];
        a+=(float)((int)(u&15)-(int)((u&8)<<1))*x0;
        b+=(float)((int)(v&15)-(int)((v&8)<<1))*x0;
        c+=(float)((int)(w&15)-(int)((w&8)<<1))*x0;
        d+=(float)((int)(z&15)-(int)((z&8)<<1))*x0;
        a+=(float)((int)(u>>4)-(int)((u&128)>>3))*x1;
        b+=(float)((int)(v>>4)-(int)((v&128)>>3))*x1;
        c+=(float)((int)(w>>4)-(int)((w&128)>>3))*x1;
        d+=(float)((int)(z>>4)-(int)((z&128)>>3))*x1;
    }
    out[0]=a;out[1]=b;out[2]=c;out[3]=d;
}
