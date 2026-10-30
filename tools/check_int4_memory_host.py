"""Independent Python checks against compiled diagnostic C, host only."""
import pathlib,subprocess,ctypes as C,json,hashlib
ROOT=pathlib.Path(__file__).resolve().parents[1];out=ROOT/'.local/int4-memory-2026-10-30';out.mkdir(exist_ok=True)
b=(ROOT/'firmware/main/microbench.h').read_text('utf-8-sig');src='#include <stdint.h>\n#include <stddef.h>\n'+b[b.index('static __attribute__'):b.index('static esp_err_t microbench')].replace('static __attribute__((noinline))','__attribute__((noinline))')
(out/'host-kernels.c').write_text(src)
subprocess.run([str(ROOT/'.local/tooling/host/ziglang/zig.exe'),'cc','-shared','-O2','-Wall','-Wextra','-Werror','-ffp-contract=off',str(out/'host-kernels.c'),'-o',str(out/'host-kernels.dll')],check=True)
l=C.CDLL(str(out/'host-kernels.dll'));l.mb_read.argtypes=[C.c_void_p,C.c_size_t];l.mb_read.restype=C.c_uint32;l.mb_unpack.argtypes=[C.c_void_p,C.c_size_t];l.mb_unpack.restype=C.c_uint32;l.mb_matrix.argtypes=[C.c_void_p,C.c_void_p];l.mb_matrix.restype=C.c_float
raw=bytes((i*37+11)%256 for i in range(1048576));buf=C.create_string_buffer(raw);x=(C.c_float*768)(*[(i%17-8)/16 for i in range(768)])
def scan(n):return sum(int.from_bytes(raw[i:i+4],'little') for i in range(0,n,4))&0xffffffff
def signed(v):return v if v<8 else v-16
unpack=sum(signed(v&15)+signed(v>>4) for v in raw[:24576])&0xffffffff
matrix=sum(sum(signed((raw[row*384+j//2]>>((j&1)*4))&15)*x[j] for j in range(768)) for row in range(64))
assert l.mb_read(buf,24576)==scan(24576) and l.mb_read(buf,1048576)==scan(1048576)
assert l.mb_unpack(buf,24576)==unpack and l.mb_matrix(buf,x)==matrix
r={'host_native_checks_passed':True,'scan_small':scan(24576),'scan_large':scan(1048576),'unpack':unpack,'matrix':matrix,'scope':'Independent Python arithmetic versus compiled diagnostic C; no host timing interpreted as P4 evidence.','script_sha256':hashlib.sha256(pathlib.Path(__file__).read_bytes()).hexdigest(),'header_sha256':hashlib.sha256((ROOT/'firmware/main/microbench.h').read_bytes()).hexdigest()}
(ROOT/'data/int4-memory-2026-10-30/host-check.json').write_text(json.dumps(r,indent=2)+'\n');print('PASS independent arithmetic and native diagnostic C')
