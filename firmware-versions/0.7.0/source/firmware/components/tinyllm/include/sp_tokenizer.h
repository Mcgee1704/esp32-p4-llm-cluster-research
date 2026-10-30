#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct sp_tokenizer sp_tokenizer;
sp_tokenizer *sp_open(const void *blob,size_t bytes,unsigned vocab,unsigned eos);
void sp_close(sp_tokenizer *t);
int sp_encode(const sp_tokenizer *t,const char *text,int *tokens,int capacity);
int sp_normalize(const sp_tokenizer *t,const char *text,void *out,size_t capacity);
const uint8_t *sp_piece(const sp_tokenizer *t,int token,size_t *length);
int sp_decode(const sp_tokenizer *t,int token,unsigned output_index,void *out,size_t capacity);
