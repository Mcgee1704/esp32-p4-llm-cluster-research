"""Local group-INT4 and static-grid GPTQ-inspired compensation, NumPy only.

Algorithm reference: Frantar et al., GPTQ, arXiv:2210.17323. Independent NumPy
implementation of fixed-grid second-order compensation; upstream Python is not
imported or executed. Whole-model validation remains required.
"""
from pack_supra import np
import struct


def _codes(w,scale,zero,scheme):
    if scheme==1:return np.clip(np.rint(w/scale),-7,7).astype('int8').view('uint8')&15
    return np.clip(np.rint(w/scale)+zero,0,15).astype('uint8')


def _values(q,scale,zero,scheme):
    values=q.astype('int16')
    values=np.where(values>=8,values-16,values) if scheme==1 else values-zero
    return values.astype('float32')*scale


def group_quantize(w,group,scheme='symmetric',shrink=(1.,.98,.96,.94,.92,.90)):
    w=np.asarray(w,dtype='float32');mode={'symmetric':1,'affine':2}.get(scheme)
    if w.ndim!=2 or not mode or not group or group&(group-1) or w.shape[1]%group or not np.isfinite(w).all():raise ValueError('Invalid group matrix')
    if not shrink or any(not 0<p<=1 for p in shrink):raise ValueError('Invalid shrink grid')
    x=w.reshape(w.shape[0],-1,group);lo=np.minimum(x.min(axis=2),0);hi=np.maximum(x.max(axis=2),0)
    best=np.full(lo.shape,np.inf);scales=np.ones(lo.shape,dtype='<f2');zeros=np.zeros(lo.shape,dtype='uint8')
    for fraction in shrink:
        original=(np.maximum(-lo,hi)/np.float32(7) if mode==1 else (hi-lo)/np.float32(15))*np.float32(fraction)
        original=np.where(original==0,1,original);scale=np.maximum(original,np.float32(2**-24)).astype('<f2')
        if not np.isfinite(scale).all():raise ValueError('FP16 scale overflow')
        sf=scale.astype('float32');zero=np.zeros(lo.shape,dtype='uint8') if mode==1 else np.clip(np.rint(-lo*np.float32(fraction)/sf),0,15).astype('uint8')
        q=_codes(x,sf[:,:,None],zero[:,:,None],mode);value=_values(q,sf[:,:,None],zero[:,:,None],mode)
        error=np.sum((x-value).astype('float64')**2,axis=2);take=error<best
        best[take]=error[take];scales[take]=scale[take];zeros[take]=zero[take]
    q=_codes(x,scales.astype('float32')[:,:,None],zeros[:,:,None],mode).reshape(w.shape)
    return {'q':q,'scale':scales,'zero':zeros,'group':int(group),'scheme':mode}


def dequantize(q):
    rows,cols=q['q'].shape;group=q['group']
    return _values(q['q'].reshape(rows,-1,group),q['scale'].astype('float32')[:,:,None],q['zero'][:,:,None],q['scheme']).reshape(rows,cols)


def inverse_factor(h,damping=.01):
    h=np.asarray(h,dtype='float64')
    if h.ndim!=2 or h.shape[0]!=h.shape[1] or not np.isfinite(h).all() or not np.allclose(h,h.T,atol=1e-7) or damping<=0:raise ValueError('Invalid calibration Hessian')
    mean=float(np.mean(np.diag(h)))
    if mean<=0:raise ValueError('No activation energy')
    h=h.copy();h.flat[::h.shape[0]+1]+=damping*mean
    try:
        inv=np.linalg.inv(h);inv=(inv+inv.T)*.5
        return np.linalg.cholesky(inv).T.astype('float32')
    except np.linalg.LinAlgError as e:raise ValueError('Non-positive calibration Hessian') from e


def gptq_quantize(w,h,grid,blocksize=128,factor=None):
    w=np.asarray(w,dtype='float32')
    if w.shape!=grid['q'].shape or np.shape(h)!=(w.shape[1],w.shape[1]) or not np.isfinite(w).all():raise ValueError('GPTQ shape or values invalid')
    if blocksize<1:raise ValueError('Invalid GPTQ block')
    upper=inverse_factor(h) if factor is None else factor
    work=w.copy();codes=np.empty(w.shape,dtype='uint8');cols=w.shape[1];group=grid['group'];scale=grid['scale'].astype('float32');zero=grid['zero']
    for start in range(0,cols,blocksize):
        end=min(start+blocksize,cols);block=work[:,start:end].copy();errors=np.zeros(block.shape,dtype='float32')
        for local,column in enumerate(range(start,end)):
            g=column//group;s=scale[:,g];z=zero[:,g];current=block[:,local].copy()
            q=_codes(current,s,z,grid['scheme']);value=_values(q,s,z,grid['scheme']);codes[:,column]=q
            error=(current-value)/upper[column,column];errors[:,local]=error
            block[:,local:]-=error[:,None]*upper[column,column:end][None,:]
        if end<cols:work[:,end:]-=errors@upper[start:end,end:]
    return {**grid,'q':codes}


def encode_matrix(q):
    rows,cols=q['q'].shape;group=q['group'];scheme=q['scheme']
    if cols%group or cols%2 or scheme not in (1,2) or q['scale'].shape!=(rows,cols//group) or q['zero'].shape!=q['scale'].shape:raise ValueError('Invalid packed matrix dimensions')
    if not np.isfinite(q['scale']).all() or np.any(q['scale']<=0) or np.any(q['q']>15) or np.any(q['zero']>15):raise ValueError('Invalid packed matrix values')
    raw=struct.pack('<4I',scheme,group,rows,cols)+q['scale'].astype('<f2').tobytes()
    if scheme==2:raw+=q['zero'].astype('uint8').tobytes()
    raw+=(q['q'][:,::2]|(q['q'][:,1::2]<<4)).tobytes();raw+=bytes(-len(raw)%4)
    return raw


def matrix_bytes(q):return len(encode_matrix(q))
