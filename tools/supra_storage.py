"""Lossless zlib flash envelope; expanded INT4 bytes and model identity unchanged."""
import hashlib
import struct
import zlib
MAX_EXPANDED=32*1024*1024


def wrap(raw):
    if not 128<=len(raw)<=MAX_EXPANDED or raw[:8]!=b'P4QS0001':raise ValueError('Invalid inner artifact')
    data=zlib.compress(raw,9);header=bytearray(128);header[:8]=b'P4ZL0001'
    struct.pack_into('<I',header,8,len(raw));struct.pack_into('<I',header,36,len(data))
    header[48:80]=hashlib.sha256(header[:48]+data).digest();struct.pack_into('<I',header,80,zlib.crc32(data))
    header[84:116]=hashlib.sha256(raw).digest()
    return bytes(header)+data


def unwrap(blob):
    if len(blob)<128 or blob[:8]!=b'P4ZL0001':raise ValueError('Wrong flash envelope')
    size=struct.unpack_from('<I',blob,8)[0];stored=struct.unpack_from('<I',blob,36)[0]
    if not 128<=size<=MAX_EXPANDED or stored!=len(blob)-128 or any(blob[12:36]+blob[40:48]+blob[116:128]):raise ValueError('Envelope bounds/flags invalid')
    data=blob[128:]
    if hashlib.sha256(blob[:48]+data).digest()!=blob[48:80] or zlib.crc32(data)!=struct.unpack_from('<I',blob,80)[0]:raise ValueError('Compressed checksum mismatch')
    try:
        d=zlib.decompressobj();raw=d.decompress(data,size+1)
    except zlib.error as e:raise ValueError('Invalid zlib stream') from e
    if len(raw)!=size or not d.eof or d.unused_data or d.unconsumed_tail or hashlib.sha256(raw).digest()!=blob[84:116] or raw[:8]!=b'P4QS0001':raise ValueError('Expanded checksum/length mismatch')
    return raw
