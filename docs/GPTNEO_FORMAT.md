# P4GN0001: bounded GPT-Neo model format

Little-endian; FP32 activations/KV, signed row INT8 matrices with FP32 scales.
This is a project format, not GGUF or a general Transformers checkpoint loader.
P4LM0001 remains the separate existing Llama layout. The initial audited model
is TinyTalk-2 revision `2b55040281013975a4d97e3db8d634f78b31c6b1`.

## Framing

128-byte header:

| Offset | Type | Meaning |
| --- | --- | --- |
| 0 | 8 bytes | ASCII `P4GN0001` |
| 8 | 7 u32 | dim, FFN, layers, heads, KV heads, vocab, runtime context |
| 36 | u32 | weight section bytes, divisible by four |
| 40 | u32 | tokenizer section bytes |
| 44 | u32 | flags, zero in this version |
| 48 | 32 bytes | SHA-256 of header bytes 0–47 followed by complete body |
| 80 | u32 | IEEE CRC32 of complete body |
| 84 | 44 bytes | exporter writes zero; no version-1 semantics |

Total size must equal 128 + weights + tokenizer, at most the 24-MiB partition.
LAN upload and boot load check SHA-256; the portable parser checks framing,
dimensions, CRC, finite scales/vectors and complete section consumption.
The hash is integrity/identity, not a cryptographic signature or authorization;
LAN authorization remains the installation's private shared key.

## Weights, in order

The body begins with three authenticated u32 values: learned position-row count,
local window, EOS ID. These are inside both the CRC and model identity hash.

- Token embedding matrix, then learned position embedding matrix.
- For each layer: LN1 weight/bias; Q, K, V, O matrices; O bias; LN2 weight/bias;
  FFN up matrix/bias; FFN down matrix/bias.
- Final LayerNorm weight/bias.

Each matrix is `rows` FP32 scales followed by `rows * cols` int8 values, row-major.
Each vector contains FP32 values. No output matrix duplicate: embedding is tied.
Quantization is symmetric max-absolute/127 per row with round-to-even and clamp
[-127,127]; all-zero rows use scale 1. Positions are quantized the same way.
Fixed semantics: LayerNorm epsilon 1e-5, GELU-new tanh approximation, causal
attention alternating global/even and local/odd, unscaled QK, no RoPE or GQA.
Metadata never requests executing model-repository code.

## Tokenizer: G2BP0001

Header: 8-byte magic `G2BP0001`, then four u32 values: vocabulary count, merge
count, string bytes, Unicode range count. Next:

1. `vocab + 1` u32 offsets, zero first and exact string-byte count last.
2. Concatenated raw byte pieces; lengths 1–512, NUL permitted. Padding to four bytes.
3. Merge records `(left ID, right ID, rank, result ID)`, four u32 each, sorted by
   `(left,right)`. Ranks are unique 0..count-1. Result bytes must equal the two
   input pieces concatenated. IDs must be in range and cannot be EOS.
4. Unicode records `(first scalar,last scalar,class)`, three u32 each, sorted
   and non-overlapping; classes 1 letter, 2 number, 3 regex whitespace. Other
   valid scalars are punctuation/other. UTF-8 input must be well formed.

All 256 singleton bytes must be present once. EOS must decode to the literal
13-byte `<|endoftext|>` marker. Special markers are split before regex-equivalent
pretokenization. No implicit BOS or leading space is added. Contractions,
optional ASCII-space prefixes and trailing-whitespace lookahead follow GPT-2's
ByteLevel pattern. Repeated lowest-ranked adjacent merges use leftmost tie order.

The exporter derives the character classes from the pinned tokenizers 0.22.1
ByteLevel backend across every valid Unicode scalar, rather than assuming the
host C locale or a different Unicode database. The initial model has 831 ranges,
50,257 pieces and 50,000 merges. String/merge/range tables remain in the model
blob; only a small byte-ID map is built at load time. Temporary rank validation
storage is released before inference.

`ts_decode_length` supplies byte lengths; callers must not use `strlen` for GPT-2.
`ts_is_eos` and `ts_architecture` expose architecture-specific behaviour while
the single-owner layer/core/RPC API remains shared. Encoding is bounded to
4,096 input bytes by the core; the HTTP interface retains its 1,024-byte prompt
limit. BPE uses bounded scratch storage; long pieces use a simple repeated-scan
algorithm rather than claiming constant-time preprocessing.

## LAN loading contract

From firmware 0.5.3 a verified P4GN upload commits its header last, returns an
acknowledgement and automatically reboots. The model is then loaded before
network allocations on a fresh heap. Dispatcher maintenance remains active
until reboot; new HTTP generation/upload requests are refused while restart is pending.
P4LM retains its established in-place loading behaviour. Clients must wait for
the expected model ID, a new boot ID and readiness, rather than treating upload
acknowledgement as completed loading. Status exposes total/largest free PSRAM
and the request/total/largest values captured immediately before model allocation.
Firmware 0.5.5 schedules restart through a checked worker created at boot and
stops Ethernet before the system restart. Successful upload acknowledgement
still precedes actual reboot/readiness; it is not a completed-loading response.
