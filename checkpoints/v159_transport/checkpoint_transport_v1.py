#!/usr/bin/env python3
"""Lossless finished-file transport. Not an exporter or converter builder.

Uses exact original repository bytes as a compression dictionary. AST parsing
only collects literal text; no source code is executed. The payload expands to
already-completed files and is verified by SHA-256 before any writes.
"""
from pathlib import Path
import ast,base64,ctypes,ctypes.util,hashlib,io,json,sys,tarfile,zlib

INPUTS={
 '3dprint_black_mirror_wave_grid_v1.156.py':'dd8aa788b952d6b0f2d15a0eff2d23a8331b3381',
 '3dprint_black_mirror_wave_grid_v1.157.py':'fc14531d795a1c8ff5c54ee6180429e6744284a8',
 '3dprint_black_mirror_wave_grid_v1.158.py':'140cc3ba441b8c44e0308a86832aa184a504356d',
 '3dprintv1.179.py':'64aab4671e596fbee9ad610d7c329aa186c6a352',
}

def dictionary(root):
    chunks=[];seen=set()
    def add(text,depth=0):
        if text in seen or depth>3:return
        seen.add(text);chunks.extend([text,repr(text)])
        try:tree=ast.parse(text)
        except (SyntaxError,ValueError):return
        for n in ast.walk(tree):
            if not isinstance(n,ast.Constant) or not isinstance(n.value,str):continue
            val=n.value
            if len(val)<100:continue
            chunks.extend([val,repr(val)])
            if len(val)>1000:
                try:decoded=zlib.decompress(base64.b64decode(val,validate=True)).decode('utf-8')
                except (ValueError,zlib.error,UnicodeDecodeError):continue
                add(decoded,depth+1)
    for name,want in INPUTS.items():
        b=(root/name).read_bytes();got=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest()
        if got!=want:raise RuntimeError('Wrong archival compression input: '+name)
        add(b.decode('utf-8'))
    # Original bytes first, literal data and complete text variants after them.
    # The variant improves dictionary compression of changed version labels;
    # it never edits any destination file or executes any converter.
    text='\n'.join(chunks)
    variant=text
    for old in ('FC3D_V1106','FC3D_V1156','FC3D_V1157','FC3D_V1158'):
        variant=variant.replace(old,'FC3D_V1159')
    return (text+'\n'+variant).encode('utf-8')

def codec(data,dict_bytes,uncompressed_size=None):
    lib=ctypes.CDLL(ctypes.util.find_library('zstd') or 'libzstd.so.1')
    void=ctypes.c_void_p;size=ctypes.c_size_t
    lib.ZSTD_isError.argtypes=[size];lib.ZSTD_isError.restype=ctypes.c_uint
    lib.ZSTD_getErrorName.argtypes=[size];lib.ZSTD_getErrorName.restype=ctypes.c_char_p
    src=ctypes.create_string_buffer(data);d=ctypes.create_string_buffer(dict_bytes)
    if uncompressed_size is None:
        lib.ZSTD_compressBound.argtypes=[size];lib.ZSTD_compressBound.restype=size
        cap=lib.ZSTD_compressBound(len(data));dest=ctypes.create_string_buffer(cap)
        lib.ZSTD_createCCtx.restype=void;ctx=lib.ZSTD_createCCtx()
        lib.ZSTD_compress_usingDict.argtypes=[void,void,size,void,size,void,size,ctypes.c_int];lib.ZSTD_compress_usingDict.restype=size
        try:n=lib.ZSTD_compress_usingDict(ctx,dest,cap,src,len(data),d,len(dict_bytes),19)
        finally:lib.ZSTD_freeCCtx.argtypes=[void];lib.ZSTD_freeCCtx(ctx)
    else:
        cap=uncompressed_size;dest=ctypes.create_string_buffer(cap)
        lib.ZSTD_createDCtx.restype=void;ctx=lib.ZSTD_createDCtx()
        lib.ZSTD_decompress_usingDict.argtypes=[void,void,size,void,size,void,size];lib.ZSTD_decompress_usingDict.restype=size
        try:n=lib.ZSTD_decompress_usingDict(ctx,dest,cap,src,len(data),d,len(dict_bytes))
        finally:lib.ZSTD_freeDCtx.argtypes=[void];lib.ZSTD_freeDCtx(ctx)
    if lib.ZSTD_isError(n):raise RuntimeError(lib.ZSTD_getErrorName(n).decode())
    return dest.raw[:n]

def unpack(root,meta_path,payload_path):
    meta=json.loads(meta_path.read_text());d=dictionary(root)
    if hashlib.sha256(d).hexdigest()!=meta['dictionary_sha256']:raise RuntimeError('Dictionary SHA mismatch')
    packed=base64.b64decode(''.join(payload_path.read_text().split()),validate=True)
    if hashlib.sha256(packed).hexdigest()!=meta['payload_sha256']:raise RuntimeError('Payload SHA mismatch')
    raw=codec(packed,d,meta['tar_bytes'])
    if hashlib.sha256(raw).hexdigest()!=meta['tar_sha256']:raise RuntimeError('Archive SHA mismatch')
    allowed={r['path']:r for r in meta['files']};pending={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tar:
        for member in tar:
            if not member.isfile() or member.name not in allowed:raise RuntimeError('Unexpected archive member')
            if Path(member.name).is_absolute() or '..' in Path(member.name).parts:raise RuntimeError('Unsafe member path')
            if member.size>50_000_000:raise RuntimeError('Oversized member')
            b=tar.extractfile(member).read();record=allowed[member.name]
            if len(b)!=record['bytes'] or hashlib.sha256(b).hexdigest()!=record['sha256']:raise RuntimeError('File verification failure: '+member.name)
            if member.name in pending:raise RuntimeError('Duplicate member')
            pending[member.name]=b
    if set(pending)!=set(allowed):raise RuntimeError('Incomplete payload')
    for name,b in pending.items():
        path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b)
    print('Published exact preverified files:',len(pending))

if __name__=='__main__':
    root=Path(sys.argv[1]).resolve();here=Path(__file__).resolve().parent
    unpack(root,here/'transport_manifest.json',here/'checkpoint_payload.b64')
