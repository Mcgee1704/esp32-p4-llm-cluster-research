#pragma once
#include <stddef.h>
#include <stdint.h>
typedef struct gpt2_tokenizer gpt2_tokenizer;
gpt2_tokenizer *gpt2_open(const uint8_t *blob,size_t bytes,unsigned vocab,unsigned eos);
void gpt2_close(gpt2_tokenizer *t);
int gpt2_encode(const gpt2_tokenizer *t,const char *text,int *tokens,int capacity);
const uint8_t *gpt2_piece(const gpt2_tokenizer *t,int token,size_t *length);
