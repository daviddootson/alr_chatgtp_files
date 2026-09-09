#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys, math, time, json, csv
from pathlib import Path
import numpy as np

# Reuse the already validated material/ray machinery and current WWK reference.
CAP=Path(__file__).resolve().parent.parent/'ALR_cap_geometry_v1.0'/'cap_geometry_study_v1.py'
sp=importlib.util.spec_from_file_location('capref',CAP)
cap=importlib.util.module_from_spec(sp);sys.modules[sp.name]=cap;sp.loader.exec_module(cap)
base=cap.base; matmod=base.mat; geo=base.geo

H=0.0
VIEW_OFFSETS=cap.VIEW_OFFSETS
VIEW_WEIGHTS=cap.VIEW_WEIGHTS

# WK is the 2-1 pyramid: bottom K,W; top K. 0.4 mm beads.
def stack_wk(c,w_dose,k_dose,scale):
    b,p,v,tilt=geo.frame(c,H)
    wh=w_dose*scale; kh=k_dose*scale
    bases=np.array([0.,wh])
    shifts=bases/np.tan(tilt)
    rows=[]
    # bottom tier 2 roads: rear/support K then leading/working W
    for i in range(2): rows.append((shifts[0]+(i+.5)*.4,bases[0],0,i,wh,1. if i==1 else 0.))
    # top single K, same canonical tilt-derived placement law
    rows.append((shifts[1]+.2,bases[1],1,0,kh,0.))
    return b,np.array(rows,float)

def white_samples(c,w_dose,k_dose,scale,count=128):
    b,roads=stack_wk(c,w_dose,k_dose,scale);a=.2;h=w_dose*scale
    phi=(np.arange(count)+.5)*np.pi/(2*count);co=np.cos(phi);si=np.sin(phi)
    w=np.hypot(a*si,h*co)*np.pi/(2*count);norm=np.hypot(h*co,a*si)
    row=roads[roads[:,2]==0];uc=float(row[-1,0]);basez=float(row[-1,1]);u=uc+a*co
    pts=np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,basez+h*si])
    normals=np.column_stack([b[0]*h*co/norm,b[1]*h*co/norm,a*si/norm])
    return pts,normals,w,np.zeros(count,int)

def ray_mask(points,normals,c,w_dose,k_dose,scale,target=geo.PROJECTOR):
    b,roads=stack_wk(c,w_dose,k_dose,scale);ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0;q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=.2
    uc=roads[:,0][None,:];basez=roads[:,1][None,:];hh=roads[:,4][None,:]
    lo=np.maximum(1e-5,(basez-h0)/rh);hi=np.minimum(dist[:,None],(basez+hh-h0)/rh)
    v0=h0-basez;aa=(dq/a)**2+(rh/hh)**2
    bb=2*((q0-uc)*dq/a**2+v0*rh/hh**2);cc=((q0-uc)/a)**2+(v0/hh)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)))
    blocked=np.any((hi>lo)&((aa*t*t+bb*t+cc)<-1e-8),axis=1)
    return facing&~blocked

def physical_gap(c,c1,w_dose,k_dose,scale):
    _,r0=stack_wk(c,w_dose,k_dose,scale);_,r1=stack_wk(c1,w_dose,k_dose,scale);d=float(np.linalg.norm(c1-c));g=[]
    for t,count in ((0,2),(1,1)):
        a=r0[r0[:,2]==t];b=r1[r1[:,2]==t]
        shift=float(b[-1,0]-a[-1,0]);g.append(d+shift-count*.4)
    return min(g)

def actual_white_fraction(c,w,k,s,pitch,samples_n=128):
    samples=white_samples(c,w,k,s,samples_n);own=ray_mask(samples[0],samples[1],c,w,k,s)
    c1=geo.advance(c,pitch,H);mask=own&ray_mask(samples[0],samples[1],c1,w,k,s)
    return geo.white_fraction(samples,mask),geo.white_fraction(samples,own)

def pitch_valid(c,w,k,s,V,pitch,samples_n=128):
    samples=white_samples(c,w,k,s,samples_n);own=ray_mask(samples[0],samples[1],c,w,k,s)
    if geo.white_fraction(samples,own)<V/100-1e-9:return False
    c1=geo.advance(c,pitch,H)
    if physical_gap(c,c1,w,k,s)<-1e-12:return False
    mask=own&ray_mask(samples[0],samples[1],c1,w,k,s)
    return geo.white_fraction(samples,mask)>=V/100-1e-9

def solve_pitch(c,w,k,s,V,samples_n=128):
    lo=.8
    if pitch_valid(c,w,k,s,V,lo,samples_n):return lo
    hi=lo
    for _ in range(80):
        hi*=1.12
        if pitch_valid(c,w,k,s,V,hi,samples_n):break
        if hi>8:return np.nan
    for _ in range(28):
        mid=(lo+hi)/2
        if pitch_valid(c,w,k,s,V,mid,samples_n):hi=mid
        else:lo=mid
    return hi

def polygons(c,w,k,s,segments=40):
    b,roads=stack_wk(c,w,k,s);power=geo.volume_power(s);a=.2
    theta=np.linspace(np.pi,0,segments+1);xx=a*np.sign(np.cos(theta))*np.abs(np.cos(theta))**(2/power)
    shapes=[];colours=[]
    for uc,basez,t,i,h,rho in roads:
        zz=h*np.sin(theta)**(2/power);shapes.append(np.column_stack([uc+xx,basez+zz]));colours.append(1. if rho>.5 else .025)
    return np.array(shapes),np.array(colours)

def geometry_kernel(c,w,k,s,pitch,viewer_offset,nrays,segments,nambient):
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]]);polys,colours=polygons(c,w,k,s,segments)
    sources=np.vstack([p,matmod.source_directions(nambient)]);lights=np.column_stack([sources[:,:2]@b,sources[:,:2]@a,sources[:,2]])
    target=geo.VIEWER+np.array([viewer_offset,0.,0.]);v=geo.unit(target-np.r_[c,0.]);local_v=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polys,colours,pitch,local_v[0]/local_v[2],nrays)
    normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=matmod.collect_kernel(polys,pitch,hits,lights,index,len(normals))
    gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(local_v[0]/local_v[2])**2)
    return dict(kernel=kernel,normals=normals,lights=lights,viewer=local_v,lit_white_fraction=float(lit.mean()),dark_band_mm=float(gap))

def prepare_material():return cap.prepare_material()
def response(coeff):return cap.resp_from_coeff(coeff)

def score_case(w,k,s,V,rays=112,segments=28,ambient=56,grid=1,view_offsets=(0.,),white_samples_n=96,material=None):
    if material is None:material=prepare_material()
    points=geo.card_points('1-2',3)[4:5] if grid==1 else geo.card_points('1-2',grid)
    by={float(v):[] for v in view_offsets};geom={float(v):[] for v in view_offsets};pitches=[];fracs=[];ownfracs=[]
    for c in points:
        pitch=solve_pitch(c,w,k,s,V,white_samples_n)
        if not np.isfinite(pitch):return None
        frac,own=actual_white_fraction(c,w,k,s,pitch,white_samples_n);pitches.append(pitch);fracs.append(frac);ownfracs.append(own)
        for vo in view_offsets:
            g=geometry_kernel(c,w,k,s,pitch,vo,rays,segments,ambient)
            coeff=matmod.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
            by[float(vo)].append(response(coeff));geom[float(vo)].append((g['dark_band_mm'],g['lit_white_fraction']))
    out={}
    for vo in view_offsets:
        aa=np.array(by[float(vo)]);gg=np.array(geom[float(vo)])
        out[float(vo)]={'response':aa.mean(axis=0),'dark_band_mm':float(gg[:,0].mean()),'lit_white_fraction':float(gg[:,1].mean())}
    return {'views':out,'pitch_mean_mm':float(np.mean(pitches)),'pitch_min_mm':float(np.min(pitches)),'pitch_max_mm':float(np.max(pitches)),
            'actual_white_fraction_mean':float(np.mean(fracs)),'own_white_fraction_mean':float(np.mean(ownfracs)),
            'total_height_mm':float((w+k)*s)}

def metrics(score,weights,offsets):
    B=np.array([score['views'][float(v)]['response'][0] for v in offsets]);A=np.array([score['views'][float(v)]['response'][1] for v in offsets])
    D=np.array([score['views'][float(v)]['dark_band_mm'] for v in offsets]);L=np.array([score['views'][float(v)]['lit_white_fraction'] for v in offsets])
    bw=float(B@weights);aw=float(A@weights)
    return {'B_raw':bw,'A_raw':aw,'C_raw':bw/aw,'dark_band_mm':float(D@weights),'lit_white_fraction':float(L@weights),'B_views':B,'A_views':A,'C_views':B/A,'dark_views':D}

def idx(m,ref):return {'B':100*m['B_raw']/ref['B_raw'],'A':100*m['A_raw']/ref['A_raw'],'C':100*m['C_raw']/ref['C_raw']}

def run_broad():
    out=Path(__file__).resolve().parent/'results';out.mkdir(exist_ok=True)
    material=prepare_material();centre=(0.,);weights=np.array([1.])
    # current champion low-res using same machinery/ray settings
    cap.W_DOSE=.24;cap.K_DOSE=.16;cap.SCALE=1.3;cap.V=77.
    rscore=cap.score_layout('single',0,112,28,56,grid=1,view_offsets=centre,white_samples_n=96,material=material);rmet=cap.weighted_metrics(rscore,weights=weights,offsets=centre)
    print('rough reference',rscore['pitch_mean_mm'],rmet['dark_band_mm'],flush=True)
    W=np.arange(.12,.281,.02);K=np.arange(.06,.181,.02);S=(1.0,1.1,1.2,1.3);VV=range(45,86,5)
    rows=[];t0=time.time();n=0
    for s in S:
      for w in W:
       for k in K:
        for V in VV:
         n+=1
         sc=score_case(float(w),float(k),float(s),float(V),material=material)
         if sc is None:
            rows.append({'W':w,'K':k,'S':s,'V':V,'feasible':False});continue
         m=metrics(sc,weights,centre);ii=idx(m,rmet)
         # broad screen: no more than 20% worse on either C/A initially; preserves near-misses for refinement
         keep=(ii['C']>=80 and ii['A']<=125 and ii['B']>=75)
         rows.append({'W':w,'K':k,'S':s,'V':V,'feasible':True,'pitch':sc['pitch_mean_mm'],'dark':m['dark_band_mm'],'height':sc['total_height_mm'],'white':sc['actual_white_fraction_mean'],'ownwhite':sc['own_white_fraction_mean'],'B':ii['B'],'A':ii['A'],'C':ii['C'],'keep20':keep})
    print('broad done',n,'sec',time.time()-t0,flush=True)
    fields=sorted({kk for r in rows for kk in r});
    with (out/'broad.csv').open('w',newline='') as f:wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(rows)
    good=[r for r in rows if r.get('keep20')]
    good.sort(key=lambda r:(-r['C'],r['pitch']))
    print('kept',len(good));print(json.dumps(good[:30],indent=2),flush=True)
    return rows,rmet

if __name__=='__main__':run_broad()
