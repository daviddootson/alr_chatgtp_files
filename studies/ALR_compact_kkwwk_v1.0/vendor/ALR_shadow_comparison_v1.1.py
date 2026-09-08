#!/usr/bin/env python3
"""ALR local paired-spacing reconstruction v1.1 (analysis only, not a converter).

Reconstructs the read v154 profile and v155/156 white-quarter point constraints.
IMPORTANT: solves independently at local card positions. Does NOT recreate the
full curved-road lattice, its phase, or the mapped solver's full-arc enlargement.
No printer files are edited or emitted. Optical scores are new-model predictions.
"""
from __future__ import annotations
import argparse, json, math, time
from pathlib import Path
from functools import lru_cache
import numpy as np
from scipy.special import gammaln
from scipy.optimize import brentq
from numba import njit
VERSION='1.1'
WIDTH=2540*16/np.sqrt(337); HEIGHT=2540*9/np.sqrt(337)
PROJECTOR=np.array([WIDTH/2,-225.,470.])
VIEWER=np.array([WIDTH/2,0.,2500.])
FILAMENT_AREA=np.pi*(1.75/2)**2

def unit(a): return a/np.linalg.norm(a)

def frame(c,horizontal=0.):
    p=unit(PROJECTOR-np.r_[c,0.]);v=unit(VIEWER-np.r_[c,0.])
    n=unit(p+v);r=np.linalg.norm(n[:2]);b=n[:2]/r;tilt=np.arctan2(r,n[2])
    if horizontal:
        theta=np.arctan2(b[1],b[0]);delta=(-np.pi/2-theta+np.pi)%(2*np.pi)-np.pi
        angle=theta+delta*horizontal/100;b=np.array([np.cos(angle),np.sin(angle)])
    return b,p,v,tilt

def card_points(piece='1-2',number=3):
    col,row=map(int,piece.split('-'));tw=WIDTH/5;th=HEIGHT/5
    w=WIDTH/20;h=124.5;x0=(col-1)*tw+(tw-w)/2;y0=(row-1)*th+(th-h)/2
    return [np.array([x0+w*x,y0+h*y]) for y in np.linspace(0,1,number) for x in np.linspace(0,1,number)]

def advance(c,d,H):
    b=frame(c,H)[0];return c+d*frame(c+b*d*.5,H)[0]

def stack(c,mapping,dose,scale,H):
    b,p,v,tilt=frame(c,H);h=dose*scale;du=h/np.tan(tilt);n=len(mapping)
    roads=np.array([(t*du+(i+.5)*.4,t*h,t,i) for t in range(n) for i in range(n-t)])
    return b,roads,du

def white_samples(c,mapping,dose,scale,H,count=256):
    b,roads,du=stack(c,mapping,dose,scale,H);h=dose*scale;a=.2
    phi=(np.arange(count)+.5)*np.pi/(2*count);co=np.cos(phi);si=np.sin(phi)
    w=np.hypot(a*si,h*co)*np.pi/(2*count);norm=np.hypot(h*co,a*si)
    points=[];normals=[];weights=[];ids=[]
    for t,char in enumerate(mapping):
        if char!='W':continue
        u=t*du+(len(mapping)-t-.5)*.4+a*co
        points.append(np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,t*h+h*si]))
        normals.append(np.column_stack([b[0]*h*co/norm,b[1]*h*co/norm,a*si/norm]))
        weights.append(w);ids.extend([t]*count)
    if not points:raise ValueError('No white working road')
    return np.concatenate(points),np.concatenate(normals),np.concatenate(weights),np.array(ids)

def white_ray_mask(points,normals,c,mapping,dose,scale,H,target=PROJECTOR):
    b,roads,_=stack(c,mapping,dose,scale,H)
    ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0
    q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=.2;h=dose*scale
    uc=roads[:,0][None,:];base=roads[:,1][None,:]
    lo=np.maximum(1e-5,(base-h0)/rh);hi=np.minimum(dist[:,None],(base+h-h0)/rh)
    v0=h0-base;aa=(dq/a)**2+(rh/h)**2
    bb=2*((q0-uc)*dq/a**2+v0*rh/h**2)
    cc=((q0-uc)/a)**2+(v0/h)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)))
    blocked=np.any((hi>lo)&((aa*t*t+bb*t+cc)<-1e-8),axis=1)
    return facing&~blocked

def white_fraction(samples,mask):
    _,_,weights,tiers=samples
    return min(float(weights[(tiers==t)&mask].sum()/weights[tiers==t].sum()) for t in np.unique(tiers))

def profile_samples(c,mapping,dose,scale,H,count=49):
    b,roads,_=stack(c,mapping,dose,scale,H);h=dose*scale;a=.2
    out=[]
    for height in np.linspace(0,len(mapping)*h,count):
        dz=height-roads[:,1];sel=(dz>=-1e-12)&(dz<=h+1e-12)
        q=np.clip(dz[sel],0,h)
        u=np.max(roads[sel,0]+a*np.sqrt(np.maximum(0,1-(q/h)**2)))
        out.append([c[0]+b[0]*u,c[1]+b[1]*u,height])
    points=np.array(out);lengths=np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
    return points,lengths/lengths[-1]

def profile_margin(points,c,mapping,dose,scale,H):
    if not len(points):return np.inf
    b,roads,_=stack(c,mapping,dose,scale,H);h=dose*scale;a=.2
    ray=PROJECTOR-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];uc=roads[:,0][None,:];base=roads[:,1][None,:]
    lo=np.maximum(0.,(base-h0)/rh);hi=np.minimum(dist[:,None],(base+h-h0)/rh)
    v0=h0-base;aa=(dq/a)**2+(rh/h)**2
    bb=2*((q0-uc)*dq/a**2+v0*rh/h**2);cc=((q0-uc)/a)**2+(v0/h)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)))
    return float(np.min(np.where(hi>=lo-1e-12,aa*t*t+bb*t+cc,np.inf)))

def solve_pitch(c,mapping,dose,scale,V,H,floor,law):
    if law not in ('profile','white'):raise ValueError(law)
    n=len(mapping);du0=stack(c,mapping,dose,scale,H)[2]
    if law=='white':
        samples=white_samples(c,mapping,dose,scale,H)
        own=white_ray_mask(samples[0],samples[1],c,mapping,dose,scale,H)
        if white_fraction(samples,own)<V/100-1e-9:return np.nan
    else:
        points,fractions=profile_samples(c,mapping,dose,scale,H)
        required=np.linspace(0,1,49);required=required[required>=1-V/100-1e-12]
        points=points[fractions>=required[0]-1e-12] if V>0 else points[:0]
    def valid(d):
        c1=advance(c,d,H);du1=stack(c1,mapping,dose,scale,H)[2]
        physical=min(np.linalg.norm(c1-c)+t*(du1-du0)-(n-t)*.4 for t in range(n))
        if physical<-1e-12:return False
        if law=='profile':return profile_margin(points,c1,mapping,dose,scale,H)>=1e-5
        mask=own&white_ray_mask(samples[0],samples[1],c1,mapping,dose,scale,H)
        return white_fraction(samples,mask)>=V/100-1e-9
    lo=max(floor,n*.4)
    if valid(lo):return lo
    hi=max(lo,.45)
    for _ in range(80):
        hi*=1.15
        if valid(hi):break
        if hi>max(8,n*.4*5):return np.nan
    for _ in range(28):
        mid=(lo+hi)/2
        if valid(mid):hi=mid
        else:lo=mid
    return hi

@lru_cache(None)
def volume_power(scale):
    target=.1567*FILAMENT_AREA/(.4*scale)
    return brentq(lambda n:np.exp(2*gammaln(1+1/n)-gammaln(1+2/n))-target,.5,20)

def section_area(a,h,power):
    return 2*a*h*np.exp(2*gammaln(1+1/power)-gammaln(1+2/power))

def ambient_directions(count):
    z=(np.arange(count)+.5)/count;phi=np.arange(count)*np.pi*(3-np.sqrt(5));r=np.sqrt(1-z*z)
    return np.column_stack([r*np.cos(phi),r*np.sin(phi),z])

def polygons(c,mapping,dose,scale,H,segments=64,bead='volume'):
    b,roads,_=stack(c,mapping,dose,scale,H);h=dose*scale
    power=volume_power(scale) if bead=='volume' else 2.
    a=.2 if bead!='narrow' else .1567*dose*FILAMENT_AREA/(np.pi*.5*h)
    theta=np.linspace(np.pi,0,segments+1)
    x=a*np.sign(np.cos(theta))*np.abs(np.cos(theta))**(2/power)
    z=h*np.sin(theta)**(2/power)
    shapes=[];colours=[]
    for uc,base,t,i in roads:
        shapes.append(np.column_stack([uc+x,base+z]))
        colours.append(1. if mapping[int(t)]=='W' and int(i)==len(mapping)-int(t)-1 else .025)
    return np.array(shapes),np.array(colours)

@njit(cache=False)
def first_hits(polys,rhos,pitch,slope,nrays):
    q=(np.arange(nrays)+.5)*pitch/nrays
    z=np.zeros(nrays);nu=np.zeros(nrays);nz=np.ones(nrays)
    rho=np.ones(nrays)*.025;owner=np.ones(nrays,np.int64)*-1;period=np.zeros(nrays,np.int64)
    for b in range(len(polys)):
        for s in range(len(polys[b])-1):
            x0,h0=polys[b,s];x1,h1=polys[b,s+1]
            du=x1-x0;dh=h1-h0;length=np.sqrt(du*du+dh*dh)
            nn_u=-dh/length;nn_z=du/length
            if nn_u*slope+nn_z<=0:continue
            q0=x0-slope*h0;q1=x1-slope*h1
            if abs(q1-q0)<1e-14:continue
            amin=min(q0,q1);amax=max(q0,q1)
            kmin=int(np.floor(-amax/pitch))-1;kmax=int(np.ceil((pitch-amin)/pitch))+1
            for k in range(kmin,kmax+1):
                left=amin+k*pitch;right=amax+k*pitch
                j0=max(0,int(np.ceil(left/pitch*nrays-.5)))
                j1=min(nrays-1,int(np.floor(right/pitch*nrays-.5)))
                for j in range(j0,j1+1):
                    t=(q[j]-k*pitch-q0)/(q1-q0);height=h0+t*dh
                    if height>z[j]+1e-12:
                        z[j]=height;nu[j]=nn_u;nz[j]=nn_z;rho[j]=rhos[b];owner[j]=b;period[j]=k
    return q+slope*z,z,nu,nz,rho,owner,period

@njit(cache=False)
def angular_interval(poly,offset,u,z):
    low=1e100;high=-1e100;above=False
    nv=len(poly)
    for j in range(nv):
        x=poly[j,0]+offset-u;h=poly[j,1]-z
        if h>1e-8:
            above=True;s=x/h;low=min(low,s);high=max(high,s)
        xn=poly[(j+1)%nv,0]+offset-u;hn=poly[(j+1)%nv,1]-z
        if h*hn<0:
            cross=x+(xn-x)*(-h)/(hn-h)
            if cross>1e-8:high=1e100
            elif cross<-1e-8:low=-1e100
        elif abs(h)<=1e-8 and hn>1e-8:
            if x>1e-8:high=1e100
            elif x<-1e-8:low=-1e100
        elif h>1e-8 and abs(hn)<=1e-8:
            if xn>1e-8:high=1e100
            elif xn<-1e-8:low=-1e100
    return low,high,above

@njit(cache=False)
def directional_visibility(polys,pitch,u,z,owner,period,slopes,eligible):
    clear=eligible.copy();nb=len(polys);nd=len(slopes)
    near=np.zeros(nb,np.int64)
    for b in range(nb):
        centre=.5*(polys[b,0,0]+polys[b,-1,0]);k0=int(np.floor((u-centre)/pitch));near[b]=k0
        for k in range(k0-1,k0+3):
            if b==owner and k==period:continue
            lo,hi,above=angular_interval(polys[b],k*pitch,u,z)
            if not above:continue
            for j in range(nd):
                if clear[j] and slopes[j]>=lo-1e-10 and slopes[j]<=hi+1e-10:clear[j]=False
    mlo=1e100;mhi=-1e100
    for j in range(nd):
        if clear[j]:mlo=min(mlo,slopes[j]);mhi=max(mhi,slopes[j])
    if mhi<mlo:return clear
    for b in range(nb):
        top=0.
        for j in range(len(polys[b])):top=max(top,polys[b,j,1])
        dh=max(0.,top-z)
        if dh<=1e-8:continue
        xmin=polys[b,0,0];xmax=polys[b,-1,0]
        kmin=int(np.floor((u+min(0.,mlo*dh)-xmax)/pitch))-1
        kmax=int(np.ceil((u+max(0.,mhi*dh)-xmin)/pitch))+1
        for k in range(kmin,kmax+1):
            if near[b]-1<=k<=near[b]+2:continue
            if b==owner and k==period:continue
            lo,hi,above=angular_interval(polys[b],k*pitch,u,z)
            if not above:continue
            for j in range(nd):
                if clear[j] and slopes[j]>=lo-1e-10 and slopes[j]<=hi+1e-10:clear[j]=False
    return clear

@njit(cache=False)
def evaluate_hits(polys,pitch,hits,directions):
    u,z,nu,nz,rho,owner,period=hits;nr=len(u);nd=len(directions)
    proj=np.zeros(nr);ambient=np.zeros(nr);lit=np.zeros(nr,np.bool_)
    slopes=directions[:,0]/directions[:,1]
    for i in range(nr):
        cos=nu[i]*directions[:,0]+nz[i]*directions[:,1]
        eligible=cos>1e-12
        clear=directional_visibility(polys,pitch,u[i],z[i],owner[i],period[i],slopes,eligible)
        if clear[0]:
            proj[i]=rho[i]*cos[0]
            lit[i]=rho[i]>.5
        total=0.
        for j in range(1,nd):
            if clear[j]:total+=cos[j]
        ambient[i]=rho[i]*2*total/(nd-1)
    return proj,ambient,lit

def longest_dark_fraction(lit):
    if not np.any(lit):return 1.
    start=int(np.flatnonzero(lit)[0]);arr=np.roll(lit,-start)
    best=run=0
    for value in arr:
        if value:run=0
        else:run+=1;best=max(best,run)
    return best/len(arr)

def score_local(c,case,pitch,segments=64,nrays=1536,nambient=256,bead='volume'):
    mapping=case['layer_map'];dose=case['layer_height_mm'];scale=case['physical_height_scale'];H=case['horizontal_percent']
    b,p,_,_=frame(c,H);polys,rhos=polygons(c,mapping,dose,scale,H,segments,bead)
    amb=ambient_directions(nambient);dirs=np.vstack([np.array([p[:2]@b,p[2]]),np.column_stack([amb[:,:2]@b,amb[:,2]])])
    results=[]
    for offset in (-1000.,0.,1000.):
        target=VIEWER+np.array([offset,0.,0.]);v=unit(target-np.r_[c,0.]);slope=float(v[:2]@b/v[2])
        hits=first_hits(polys,rhos,pitch,slope,nrays)
        B,A,lit=evaluate_hits(polys,pitch,hits,dirs)
        results.append({'viewer_offset_mm':offset,'B':float(np.mean(B)/p[2]),'A':float(np.mean(A)),
                        'lit_white_fraction':float(np.mean(lit)),
                        'projected_dark_band_mm':longest_dark_fraction(lit)*pitch/np.sqrt(1+slope*slope)})
    return results
