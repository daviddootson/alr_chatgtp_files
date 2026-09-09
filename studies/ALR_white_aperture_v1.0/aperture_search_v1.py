#!/usr/bin/env python3
"""WWK white-aperture / rear-support geometry search v1.0.

Analysis only; not printer G-code. Keeps the current physical champion settings
fixed (WWK, W0.24, K0.16, S1.30, V77, H0) and varies only:
  * w_shift_mm: common local-u offset of both leading white roads;
  * support_shift_mm: common local-u offset of rear black support roads on
    tiers 0 and 1. The top K cap remains at the established tilt-derived place.

Positive u is toward the leading white optical face. Negative support shift
moves the rear black support staircase away from the white optical column.
Uses the established material/ray machinery and 3-view scoring.
"""
from __future__ import annotations
import importlib.util, math, sys, json
from functools import lru_cache
from pathlib import Path
import numpy as np
from scipy.optimize import brentq
from scipy.special import gammaln

HERE=Path(__file__).resolve().parent
BASE=HERE.parent/'ALR_thincap_wwk_v1.0'/'ALR_thincap_wwk_v1_0.py'
sp=importlib.util.spec_from_file_location('wwkbase',BASE)
base=importlib.util.module_from_spec(sp);sys.modules[sp.name]=base;sp.loader.exec_module(base)
mat=base.mat;geo=base.geo
W=.24;K=.16;S=1.30;V=77.;H=0.;COUNTS=(3,2,1)
VIEW_OFFSETS=(-geo.WIDTH/2,0.,geo.WIDTH/2);VIEW_WEIGHTS=np.array([1/6,2/3,1/6])
FILAMENT_AREA=np.pi*(1.75/2)**2

def heights(): return np.array([W*S,W*S,K*S],float)
def bases():
    h=heights();return np.array([0.,h[0],h[0]+h[1]],float)

def stack(c,w_shift_mm=0.,support_shift_mm=0.):
    b,p,v,tilt=geo.frame(c,H);bs=bases();hs=heights();du=bs/np.tan(tilt);rows=[]
    for t,count in enumerate(COUNTS):
        for i in range(count):
            u=du[t]+(i+.5)*.4;white=t in (0,1) and i==count-1
            if white:u+=w_shift_mm
            elif t in (0,1):u+=support_shift_mm
            rows.append((u,bs[t],t,i,hs[t],1. if white else 0.))
    return b,np.array(rows,float)

def white_samples(c,w_shift_mm,support_shift_mm,count=256):
    b,r=stack(c,w_shift_mm,support_shift_mm);a=.2;h=W*S
    phi=(np.arange(count)+.5)*np.pi/(2*count);co=np.cos(phi);si=np.sin(phi)
    ww=np.hypot(a*si,h*co)*np.pi/(2*count);norm=np.hypot(h*co,a*si)
    pts=[];nn=[];weights=[];ids=[]
    for t in (0,1):
        q=r[(r[:,2]==t)&(r[:,5]>.5)][0];u=q[0]+a*co
        pts.append(np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,q[1]+h*si]))
        nn.append(np.column_stack([b[0]*h*co/norm,b[1]*h*co/norm,a*si/norm]))
        weights.append(ww);ids.extend([t]*count)
    return np.concatenate(pts),np.concatenate(nn),np.concatenate(weights),np.array(ids)

def white_fraction(samples,mask):
    weights,tiers=samples[2],samples[3]
    return min(float(weights[(tiers==t)&mask].sum()/weights[tiers==t].sum()) for t in np.unique(tiers))

def ray_mask(points,normals,c,w_shift_mm,support_shift_mm,target=geo.PROJECTOR):
    b,r=stack(c,w_shift_mm,support_shift_mm);ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0;q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=.2;uc=r[:,0][None,:];bb=r[:,1][None,:];hh=r[:,4][None,:]
    lo=np.maximum(1e-5,(bb-h0)/rh);hi=np.minimum(dist[:,None],(bb+hh-h0)/rh);v0=h0-bb
    aa=(dq/a)**2+(rh/hh)**2;bq=2*((q0-uc)*dq/a**2+v0*rh/hh**2);cc=((q0-uc)/a)**2+(v0/hh)**2-1
    tt=np.maximum(lo,np.minimum(hi,-bq/(2*aa)));blocked=np.any((hi>lo)&((aa*tt*tt+bq*tt+cc)<-1e-8),axis=1)
    return facing&~blocked

def physical_gap(c,c1,w_shift_mm,support_shift_mm):
    _,a=stack(c,w_shift_mm,support_shift_mm);_,b=stack(c1,w_shift_mm,support_shift_mm);d=float(np.linalg.norm(c1-c));g=[]
    for t in range(3):
        x=a[a[:,2]==t];y=b[b[:,2]==t];span=float(x[:,0].max()-x[:,0].min()+.4);shift=float(y[:,0].max()-x[:,0].max())
        g.append(d+shift-span)
    return min(g)

def valid(c,pitch,w_shift_mm,support_shift_mm,white_n=256):
    s=white_samples(c,w_shift_mm,support_shift_mm,white_n);own=ray_mask(s[0],s[1],c,w_shift_mm,support_shift_mm)
    if white_fraction(s,own)<V/100-1e-9:return False
    c1=geo.advance(c,pitch,H)
    if physical_gap(c,c1,w_shift_mm,support_shift_mm)<-1e-12:return False
    return white_fraction(s,own&ray_mask(s[0],s[1],c1,w_shift_mm,support_shift_mm))>=V/100-1e-9

def solve_pitch(c,w_shift_mm,support_shift_mm,white_n=256):
    _,r=stack(c,w_shift_mm,support_shift_mm);lo=max(float(np.ptp(r[r[:,2]==t,0])+.4) for t in range(3))
    if valid(c,lo,w_shift_mm,support_shift_mm,white_n):return lo
    hi=lo
    for _ in range(80):
        hi*=1.12
        if valid(c,hi,w_shift_mm,support_shift_mm,white_n):break
        if hi>8:return np.nan
    for _ in range(30):
        mid=(lo+hi)/2
        if valid(c,mid,w_shift_mm,support_shift_mm,white_n):hi=mid
        else:lo=mid
    return hi

@lru_cache(None)
def volume_power():
    target=.1567*FILAMENT_AREA/(.4*S)
    return brentq(lambda n:np.exp(2*gammaln(1+1/n)-gammaln(1+2/n))-target,.5,20)

def polygons(c,w_shift_mm,support_shift_mm,segments=128):
    _,r=stack(c,w_shift_mm,support_shift_mm);p=volume_power();a=.2;th=np.linspace(np.pi,0,segments+1)
    xx=a*np.sign(np.cos(th))*np.abs(np.cos(th))**(2/p);out=[];col=[]
    for u,z,t,i,h,white in r:
        out.append(np.column_stack([u+xx,z+h*np.sin(th)**(2/p)]));col.append(1. if white>.5 else .025)
    return np.array(out),np.array(col)

def material():
    table,avg=mat.energy_table(1.57,.22);return np.array([1.57]),np.array([.22]),np.array([table]),np.array([avg])

def response(coeff,rw=.75,rk=.025):
    a=np.asarray(coeff);return a[0,1,:,0]+rw*a[0,1,:,1]+a[0,0,:,0]+rk*a[0,0,:,1]

def geometry_kernel(c,pitch,offset,w_shift_mm,support_shift_mm,nrays,segments,nambient):
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]]);polys,colours=polygons(c,w_shift_mm,support_shift_mm,segments)
    src=np.vstack([p,mat.source_directions(nambient)]);lights=np.column_stack([src[:,:2]@b,src[:,:2]@a,src[:,2]])
    target=geo.VIEWER+np.array([offset,0.,0.]);v=geo.unit(target-np.r_[c,0.]);lv=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polys,colours,pitch,lv[0]/lv[2],nrays);normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=mat.collect_kernel(polys,pitch,hits,lights,index,len(normals));gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(lv[0]/lv[2])**2)
    return kernel,normals,lights,lv,gap

def score(w_shift_mm,support_shift_mm,rays=1536,segments=128,ambient=768,white_n=512):
    mm=material();valss={o:[] for o in VIEW_OFFSETS];gaps={o:[] for o in VIEW_OFFSETS};pitches=[]
    for c in geo.card_points('1-2',3):
        pitch=solve_pitch(c,w_shift_mm,support_shift_mm,white_n);pitches.append(pitch)
        for off in VIEW_OFFSETS]:
            k,n,l,v,g=geometry_kernel(c,pitch,off,w_shift_mm,support_shift_mm,rays,segments,ambient)
            valss[off].append(response(mat.compute_coefficients(k,n,l,v,*mm,ambient)));gaps[off].append(g)
    out={'w_shift_mm':w_shift_mm,'support_shift_mm':support_shift_mm,'pitch_mm':float(np.mean(pitches))}
    for off in VIEW_OFFSETS:
        a=np.array(vals[off]);out[f'B_{off}']=float(a[:,0].mean());out[f'A_{off}']=float(a[:,1].mean());out[f'C_{off}']=out[f'B_{off}']/out[f'A_{off}'];out[f'dark_{off}']=float(np.mean(gaps[off]))
    return out

def indices(case,ref):
    out=dict(case)
    for off in VIEW_OFFSETS:
        for key in ('B','A','C'):out[f'{key}i_{off}']=100*case[f'{key}_{off}']/ref[f'{key}_{off}']
    B=np.array([case[f'B_{o}'] for o in VIEW_OFFSETS]);A=np.array([case[f'A_{o}'] for o in VIEW_OFFSETS]);Br=np.array([ref[f'B_{o}'] for o in VIEW_OFFSETS]);Ar=np.array([ref[f'A_{o}'] for o in VIEW_OFFSETS])
    out['B_weighted_index']=100*(B@VIEW_WEIGHTS)/(Br@VIEW_WEIGHTS);out['A_weighted_index']=100*(A@VIEW_WEIGHTS)/(Ar@VIEW_WEIGHTS);out['C_weighted_index']=100*((B@VIEW_WEIGHTS)/(A@VIEW_WEIGHTS))/((Br@VIEW_WEIGHTS)/(Ar@VIEW_WEIGHTS))
    return out

def main():
    ref=score(0,0);tests=[(.004,-.175),(.005,-.16),(.006,-.17),(.0075,-.18),(.01,-.18)]
    rows=[]
    for w,s in tests:
        n=indices(score(w,s),ref);rows.append(n);print(w,s,'centre B/A/C',n['Bi_0.0'],n['Ai_0.0'],n['Ci_0.0'],'weighted',n['B_weighted_index'],n['A_weighted_index'],n['C_weighted_index'])
    Path('aperture_selected_results_v1.json').write_text(json.dumps({'reference':ref,'rows':rows},indent=2))
if __name__=='__main__':main()
