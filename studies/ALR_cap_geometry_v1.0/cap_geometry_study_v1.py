#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, sys, math, json, csv, time
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent.parent/'ALR_thincap_wwk_v1.0'
spec=importlib.util.spec_from_file_location('base_study',HERE/'ALR_thincap_wwk_v1_0.py')
base=importlib.util.module_from_spec(spec);sys.modules[spec.name]=base;spec.loader.exec_module(base)
mat=base.mat; geo=base.geo

W_DOSE=.24; K_DOSE=.16; SCALE=1.3; V=77.; H=0.
COUNTS=(3,2)
EDGE_OFFSET=float(geo.WIDTH/2)
VIEW_OFFSETS=(-EDGE_OFFSET,0.,EDGE_OFFSET)
VIEW_NAMES=('left','centre','right')
VIEW_WEIGHTS=np.array([1/6,2/3,1/6],float)

def heights(): return W_DOSE*SCALE, K_DOSE*SCALE

def stack_custom(c, mode='single', offset=0.0):
    b,p,v,tilt=geo.frame(c,H); wh,kh=heights();bases=np.array([0.,wh,2*wh]);shifts=bases/np.tan(tilt);rows=[]
    for i in range(3): rows.append((shifts[0]+(i+.5)*.4,bases[0],0,i,wh,1. if i==2 else 0.))
    for i in range(2): rows.append((shifts[1]+(i+.5)*.4,bases[1],1,i,wh,1. if i==1 else 0.))
    if mode=='single': rows.append((shifts[2]+.2+float(offset),bases[2],2,0,kh,0.))
    elif mode=='twin':
        for i in range(2): rows.append((shifts[1]+(i+.5)*.4+float(offset),bases[2],2,i,kh,0.))
    else: raise ValueError(mode)
    return b,np.array(rows,float)

def white_samples(c,count=192):
    b,roads=stack_custom(c,'single',0);a=.2; wh,_=heights(); phi=(np.arange(count)+.5)*np.pi/(2*count)
    co=np.cos(phi);si=np.sin(phi);w=np.hypot(a*si,wh*co)*np.pi/(2*count);norm=np.hypot(wh*co,a*si)
    points=[];normals=[];weights=[];ids=[]
    for t in (0,1):
        row=roads[roads[:,2]==t]; uc=float(row[-1,0]);basez=float(row[-1,1]);u=uc+a*co
        points.append(np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,basez+wh*si]))
        normals.append(np.column_stack([b[0]*wh*co/norm,b[1]*wh*co/norm,a*si/norm]))
        weights.append(w);ids.extend([t]*count)
    return np.concatenate(points),np.concatenate(normals),np.concatenate(weights),np.array(ids)

def ray_mask(points,normals,c,mode,offset,target=geo.PROJECTOR):
    b,roads=stack_custom(c,mode,offset); ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0; q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=.2;uc=roads[:,0][None,:];basez=roads[:,1][None,:];hh=roads[:,4][None,:]
    lo=np.maximum(1e-5,(basez-h0)/rh);hi=np.minimum(dist[:,None],(basez+hh-h0)/rh)
    v0=h0-basez;aa=(dq/a)**2+(rh/hh)**2;bb=2*((q0-uc)*dq/a**2+v0*rh/hh**2);cc=((q0-uc)/a)**2+(v0/hh)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)));blocked=np.any((hi>lo)&((aa*t*t+bb*t+cc)<-1e-8),axis=1)
    return facing&~blocked

def physical_gap(c,c1,mode,offset):
    _,r0=stack_custom(c,mode,offset);_,r1=stack_custom(c1,mode,offset);d=float(np.linalg.norm(c1-c));g=[]
    for t in (0,1,2):
        a=r0[r0[:,2]==t];b=r1[r1[:,2]==t];leading0=float(np.max(a[:,0]));leading1=float(np.max(b[:,0]));span=float(np.max(a[:,0])-np.min(a[:,0])+.4)
        g.append(d+(leading1-leading0)-span)
    return min(g)

def actual_white_fraction(c,mode,offset,pitch,sample_count=192):
    samples=white_samples(c,sample_count);own=ray_mask(samples[0],samples[1],c,mode,offset);c1=geo.advance(c,pitch,H);mask=own&ray_mask(samples[0],samples[1],c1,mode,offset)
    return geo.white_fraction(samples,mask)

def pitch_valid(c,mode,offset,pitch,sample_count=192):
    samples=white_samples(c,sample_count);own=ray_mask(samples[0],samples[1],c,mode,offset)
    if geo.white_fraction(samples,own)<V/100-1e-9:return False
    c1=geo.advance(c,pitch,H)
    if physical_gap(c,c1,mode,offset)<-1e-12:return False
    mask=own&ray_mask(samples[0],samples[1],c1,mode,offset)
    return geo.white_fraction(samples,mask)>=V/100-1e-9

def solve_pitch(c,mode,offset,sample_count=192):
    lo=1.2
    if pitch_valid(c,mode,offset,lo,sample_count):return lo
    hi=lo
    for _ in range(80):
        hi*=1.12
        if pitch_valid(c,mode,offset,hi,sample_count):break
        if hi>8:return np.nan
    for _ in range(30):
        mid=(lo+hi)/2
        if pitch_valid(c,mode,offset,mid,sample_count):hi=mid
        else:lo=mid
    return hi

def polygons(c,mode,offset,segments=64):
    b,roads=stack_custom(c,mode,offset);power=geo.volume_power(SCALE);a=.2
    theta=np.linspace(np.pi,0,segments+1);xx=a*np.sign(np.cos(theta))*np.abs(np.cos(theta))**(2/power)
    shapes=[];colours=[]
    for uc,basez,t,i,h,rho in roads:
        zz=h*np.sin(theta)**(2/power);shapes.append(np.column_stack([uc+xx,basez+zz]));colours.append(1. if rho>.5 else .025)
    return np.array(shapes),np.array(colours)

def geometry_kernel(c,mode,offset,pitch,viewer_offset,nrays,segments,nambient):
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]]);polys,colours=polygons(c,mode,offset,segments)
    sources=np.vstack([p,mat.source_directions(nambient)]);lights=np.column_stack([sources[:,:2]@b,sources[:,:2]@a,sources[:,2]])
    target=geo.VIEWER+np.array([viewer_offset,0.,0.]);v=geo.unit(target-np.r_[c,0.]);local_v=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polys,colours,pitch,local_v[0]/local_v[2],nrays)
    normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=mat.collect_kernel(polys,pitch,hits,lights,index,len(normals));gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(local_v[0]/local_v[2])**2)
    return dict(kernel=kernel,normals=normals,lights=lights,viewer=local_v,lit_white_fraction=float(lit.mean()),dark_band_mm=float(gap))

def prepare_material(): return base.prepare_petg_central()
def resp_from_coeff(coeff):return base.response(coeff)

def support_overlap(c,mode,offset):
    _,roads=stack_custom(c,mode,offset);w=roads[roads[:,2]==1][:,0];k=roads[roads[:,2]==2][:,0]
    if mode=='single':
        lo=min(w)-.2;hi=max(w)+.2;ka=k[0]-.2;kb=k[0]+.2;return max(0.,min(hi,kb)-max(lo,ka))/.4
    return min(max(0.,.4-abs(float(k[i]-w[i])))/.4 for i in range(2))

def score_layout(mode,offset,rays,segments,ambient,grid=1,view_offsets=(0.,),white_samples_n=192,material=None):
    if material is None: material=prepare_material()
    points=geo.card_points('1-2',3)[4:5] if grid==1 else geo.card_points('1-2',grid)
    by_view={float(v):[] for v in view_offsets}; geom={float(v):[] for v in view_offsets}; pitches=[];fracs=[];overlaps=[]
    for c in points:
        pitch=solve_pitch(c,mode,offset,white_samples_n);pitches.append(pitch)
        if not np.isfinite(pitch):return None
        frac=actual_white_fraction(c,mode,offset,pitch,white_samples_n);fracs.append(frac);overlaps.append(support_overlap(c,mode,offset))
        for vo in view_offsets:
            g=geometry_kernel(c,mode,offset,pitch,vo,rays,segments,ambient);coeff=mat.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
            by_view[float(vo)].append(resp_from_coeff(coeff));geom[float(vo)].append((g['dark_band_mm'],g['lit_white_fraction']))
    result={}
    for vo in view_offsets:
        a=np.array(by_view[float(vo)]);gg=np.array(geom[float(vo)]);result[float(vo)]={'response':a.mean(axis=0),'dark_band_mm':float(gg[:,0].mean()),'lit_white_fraction':float(gg[:,1].mean())}
    return {'views':result,'pitch_mean_mm':float(np.mean(pitches)),'pitch_min_mm':float(np.min(pitches)),'pitch_max_mm':float(np.max(pitches)),'actual_white_fraction_mean':float(np.mean(fracs)),'support_overlap_min_fraction':float(np.min(overlaps))}

def score_historical_reference(rays,segments,ambient,grid=3,view_offsets=VIEW_OFFSETS,material=None):
    if material is None:material=prepare_material()
    points=geo.card_points('1-2',3)[4:5] if grid==1 else geo.card_points('1-2',grid);by={float(v):[] for v in view_offsets};geom={float(v):[] for v in view_offsets};pitches=[]
    for c in points:
        pitch=geo.solve_pitch(c,'KWK',.20,1.2,70,0,0,'white');pitches.append(pitch)
        for vo in view_offsets:
            g=mat.geometry_kernel(c,dict(layer_map='KWK',layer_height_mm=.20,physical_height_scale=1.2,horizontal_percent=0),pitch,vo,rays,segments,ambient);coeff=mat.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
            by[float(vo)].append(resp_from_coeff(coeff));geom[float(vo)].append((g['dark_band_mm'],g['lit_white_fraction']))
    out={}
    for vo in view_offsets:
        a=np.array(by[float(vo)]);gg=np.array(geom[float(vo)]);out[float(vo)]={'response':a.mean(axis=0),'dark_band_mm':float(gg[:,0].mean()),'lit_white_fraction':float(gg[:,1].mean())}
    return {'views':out,'pitch_mean_mm':float(np.mean(pitches))}

def weighted_metrics(score, weights=VIEW_WEIGHTS, offsets=VIEW_OFFSETS):
    B=np.array([score['views'][float(v)]['response'][0] for v in offsets]);A=np.array([score['views'][float(v)]['response'][1] for v in offsets]);D=np.array([score['views'][float(v)]['dark_band_mm'] for v in offsets]);L=np.array([score['views'][float(v)]['lit_white_fraction'] for v in offsets])
    bw=float(B@weights);aw=float(A@weights)
    return {'B_raw':bw,'A_raw':aw,'C_raw':bw/aw,'dark_band_mm':float(D@weights),'lit_white_fraction':float(L@weights),'B_views':B,'A_views':A,'C_views':B/A,'dark_views':D,'lit_views':L}

def indices(metrics,ref):return {'B_index':100*metrics['B_raw']/ref['B_raw'],'A_index':100*metrics['A_raw']/ref['A_raw'],'C_index':100*metrics['C_raw']/ref['C_raw']}

def serialise(score,m):
    return {'pitch_mean_mm':score['pitch_mean_mm'],'actual_white_fraction_mean':score.get('actual_white_fraction_mean'),'support_overlap_min_fraction':score.get('support_overlap_min_fraction'),'weighted':{k:(v.tolist() if isinstance(v,np.ndarray) else v) for k,v in m.items()},'views':{str(k):{'B_raw':float(v['response'][0]),'A_raw':float(v['response'][1]),'C_raw':float(v['response'][0]/v['response'][1]),'dark_band_mm':v['dark_band_mm'],'lit_white_fraction':v['lit_white_fraction']} for k,v in score['views'].items()}}

def main():
    out=Path(__file__).resolve().parent/'results';out.mkdir(exist_ok=True);material=prepare_material();start=time.time();low=(224,44,112);centre=(0.,)
    ref_low=score_layout('single',0,*low,grid=1,view_offsets=centre,white_samples_n=128,material=material);rm=weighted_metrics(ref_low,weights=np.array([1.]),offsets=centre);rows=[]
    for mode,offsets in [('single',np.round(np.arange(-.30,.3001,.05),3)),('twin',np.round(np.arange(-.15,.1501,.025),3))]:
        for off in offsets:
            s=score_layout(mode,float(off),*low,grid=1,view_offsets=centre,white_samples_n=128,material=material)
            if s is None: rows.append(dict(mode=mode,offset_mm=float(off),feasible=False));continue
            m=weighted_metrics(s,weights=np.array([1.]),offsets=centre);ix=indices(m,rm);rows.append(dict(mode=mode,offset_mm=float(off),feasible=True,**ix,pitch_mm=s['pitch_mean_mm'],dark_band_mm=m['dark_band_mm'],lit_white_fraction=m['lit_white_fraction'],actual_white_fraction=s['actual_white_fraction_mean'],support_overlap=s['support_overlap_min_fraction']))
    with (out/'stage1.csv').open('w',newline='') as f:
        fields=sorted({k for r in rows for k in r});w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print('STAGE1_JSON',json.dumps(rows,separators=(',',':')),flush=True)
    high=(1024,96,512);ref_high=score_layout('single',0,*high,grid=3,view_offsets=VIEW_OFFSETS,white_samples_n=256,material=material);refm=weighted_metrics(ref_high)
    hist=score_historical_reference(*high,grid=3,view_offsets=VIEW_OFFSETS,material=material);histm=weighted_metrics(hist)
    print('CONTROL_JSON',json.dumps({'new_reference':serialise(ref_high,refm),'historical':serialise(hist,histm),'new_vs_historical':indices(refm,histm)},separators=(',',':')),flush=True)
    (out/'reference.json').write_text(json.dumps({'new_reference':serialise(ref_high,refm),'historical':serialise(hist,histm),'new_vs_historical':indices(refm,histm)},indent=2)+'\n');print('SECONDS',time.time()-start,flush=True)

if __name__=='__main__':main()
