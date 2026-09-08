from __future__ import annotations
import importlib.util, sys, math, json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
ROOT=HERE
spec=importlib.util.spec_from_file_location('tc',ROOT/'ALR_thincap_wwk_v1_0.py')
tc=importlib.util.module_from_spec(spec);sys.modules[spec.name]=tc;spec.loader.exec_module(tc)
mat=tc.mat; geo=tc.geo
COUNTS=(3,2,1)

def tier_heights(w_dose,k_dose,scale):
    return np.array([w_dose*scale,w_dose*scale,k_dose*scale],float)

def tier_bases(w_dose,k_dose,scale):
    h=tier_heights(w_dose,k_dose,scale)
    return np.array([0.,h[0],h[0]+h[1]],float)

def stack(c,w_dose,k_dose,scale,H,width):
    b,p,v,tilt=geo.frame(c,H);bases=tier_bases(w_dose,k_dose,scale)
    shifts=bases/np.tan(tilt);rows=[];hs=tier_heights(w_dose,k_dose,scale)
    for t,count in enumerate(COUNTS):
        for i in range(count):
            rows.append((shifts[t]+(i+.5)*width,bases[t],t,i,hs[t]))
    return b,np.array(rows,float)

def white_samples(c,w_dose,k_dose,scale,H,width,count=256):
    b,roads=stack(c,w_dose,k_dose,scale,H,width);a=width/2
    h=w_dose*scale
    phi=(np.arange(count)+.5)*np.pi/(2*count);co=np.cos(phi);si=np.sin(phi)
    weights=np.hypot(a*si,h*co)*np.pi/(2*count);norm=np.hypot(h*co,a*si)
    pts=[];norms=[];ws=[];ids=[]
    for t in (0,1):
        row=roads[roads[:,2]==t];uc=float(row[-1,0]);base=float(row[-1,1])
        u=uc+a*co
        pts.append(np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,base+h*si]))
        norms.append(np.column_stack([b[0]*h*co/norm,b[1]*h*co/norm,a*si/norm]))
        ws.append(weights);ids.extend([t]*count)
    return np.concatenate(pts),np.concatenate(norms),np.concatenate(ws),np.array(ids)

def white_ray_mask(points,normals,c,w_dose,k_dose,scale,H,width,target=geo.PROJECTOR):
    b,roads=stack(c,w_dose,k_dose,scale,H,width)
    ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0
    q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=width/2
    uc=roads[:,0][None,:];base=roads[:,1][None,:];hh=roads[:,4][None,:]
    lo=np.maximum(1e-5,(base-h0)/rh);hi=np.minimum(dist[:,None],(base+hh-h0)/rh)
    v0=h0-base;aa=(dq/a)**2+(rh/hh)**2
    bb=2*((q0-uc)*dq/a**2+v0*rh/hh**2);cc=((q0-uc)/a)**2+(v0/hh)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)))
    blocked=np.any((hi>lo)&((aa*t*t+bb*t+cc)<-1e-8),axis=1)
    return facing&~blocked

def physical_gap(c,c1,w_dose,k_dose,scale,H,width):
    _,r0=stack(c,w_dose,k_dose,scale,H,width);_,r1=stack(c1,w_dose,k_dose,scale,H,width)
    d=float(np.linalg.norm(c1-c));g=[]
    for t,count in enumerate(COUNTS):
        a=r0[r0[:,2]==t];b=r1[r1[:,2]==t]
        shift=float(b[-1,0]-a[-1,0]);g.append(d+shift-count*width)
    return min(g)

def pitch_valid(c,w_dose,k_dose,scale,V,H,width,pitch):
    samples=white_samples(c,w_dose,k_dose,scale,H,width)
    own=white_ray_mask(samples[0],samples[1],c,w_dose,k_dose,scale,H,width)
    if geo.white_fraction(samples,own)<V/100-1e-9:return False
    c1=geo.advance(c,pitch,H)
    if physical_gap(c,c1,w_dose,k_dose,scale,H,width)<-1e-12:return False
    mask=own&white_ray_mask(samples[0],samples[1],c1,w_dose,k_dose,scale,H,width)
    return geo.white_fraction(samples,mask)>=V/100-1e-9

def solve_pitch(c,w_dose,k_dose,scale,V,H,width,floor=0.):
    lo=max(float(floor),3*width)
    if pitch_valid(c,w_dose,k_dose,scale,V,H,width,lo):return lo
    hi=max(lo,.225 if width<=.2 else .45)
    for _ in range(100):
        hi*=1.12
        if pitch_valid(c,w_dose,k_dose,scale,V,H,width,hi):break
        if hi>8:return np.nan
    for _ in range(34):
        mid=(lo+hi)/2
        if pitch_valid(c,w_dose,k_dose,scale,V,H,width,mid):hi=mid
        else:lo=mid
    return hi

def actual_white_fraction(c,w_dose,k_dose,scale,H,width,pitch):
    s=white_samples(c,w_dose,k_dose,scale,H,width)
    own=white_ray_mask(s[0],s[1],c,w_dose,k_dose,scale,H,width)
    c1=geo.advance(c,pitch,H)
    mask=own&white_ray_mask(s[0],s[1],c1,w_dose,k_dose,scale,H,width)
    return geo.white_fraction(s,mask)

def polygons(c,w_dose,k_dose,scale,H,width,segments=64):
    b,roads=stack(c,w_dose,k_dose,scale,H,width)
    power=geo.volume_power(scale);a=width/2
    theta=np.linspace(np.pi,0,segments+1)
    xx=a*np.sign(np.cos(theta))*np.abs(np.cos(theta))**(2/power)
    shapes=[];colours=[]
    for uc,base,t,i,h in roads:
        zz=h*np.sin(theta)**(2/power)
        shapes.append(np.column_stack([uc+xx,base+zz]))
        t=int(t);i=int(i)
        colours.append(1. if t in (0,1) and i==COUNTS[t]-1 else .025)
    return np.array(shapes),np.array(colours)

def geometry_kernel(c,w_dose,k_dose,scale,H,width,pitch,offset,nrays,segments,nambient):
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]])
    polys,colours=polygons(c,w_dose,k_dose,scale,H,width,segments)
    sources=np.vstack([p,mat.source_directions(nambient)])
    lights=np.column_stack([sources[:,:2]@b,sources[:,:2]@a,sources[:,2]])
    target=geo.VIEWER+np.array([offset,0.,0.]);v=geo.unit(target-np.r_[c,0.])
    local_v=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polys,colours,pitch,local_v[0]/local_v[2],nrays)
    normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=mat.collect_kernel(polys,pitch,hits,lights,index,len(normals))
    gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(local_v[0]/local_v[2])**2)
    return dict(kernel=kernel,normals=normals,lights=lights,viewer=local_v,
                lit_white_fraction=float(lit.mean()),dark_band_mm=float(gap))

def score(case,ref_response,rays=512,segments=64,ambient=256,grid=3):
    w,k,s,V,width=case['w'],case['k'],case['s'],case['V'],case['width'];H=0
    material=tc.prepare_petg_central(); vals=[]; rec=[]
    points=geo.card_points('1-2',grid)
    for c in points:
        pitch=solve_pitch(c,w,k,s,V,H,width)
        frac=actual_white_fraction(c,w,k,s,H,width,pitch)
        for off in (-1000.,0.,1000.):
            g=geometry_kernel(c,w,k,s,H,width,pitch,off,rays,segments,ambient)
            coeff=mat.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
            vals.append(tc.response(coeff));rec.append((pitch,g['dark_band_mm'],g['lit_white_fraction'],frac))
    r=np.array(vals).mean(axis=0)
    B=100*r[0]/ref_response[0]; A=100*r[1]/ref_response[1]; C=100*(r[0]/r[1])/(ref_response[0]/ref_response[1])
    return dict(**case,brightness=B,ambient=A,contrast=C,
                pitch=np.mean([x[0] for x in rec]),dark=np.mean([x[1] for x in rec]),white=np.mean([x[3] for x in rec]),
                total_height=(2*w+k)*s)

def main():
    rays=1024;segments=96;ambient=512
    ref,_=tc.score_reference(rays=rays,segments=segments,ambient=ambient,grid=3)
    cases=[
      dict(label='physical_best_04',width=.4,w=.24,k=.165,s=1.2,V=75),
      dict(label='physical_best_02_half',width=.2,w=.12,k=.0825,s=1.2,V=75),
      dict(label='s13_04',width=.4,w=.24,k=.16,s=1.3,V=77),
      dict(label='s13_02_half',width=.2,w=.12,k=.08,s=1.3,V=77),
      dict(label='bright_04',width=.4,w=.22,k=.10,s=1.2,V=50),
      dict(label='bright_02_cap_floor',width=.2,w=.11,k=.08,s=1.2,V=50),
    ]
    out=[]
    for c in cases:
        print('scoring',c['label'],flush=True);out.append(score(c,ref,rays,segments,ambient,3))
    target=HERE/'nozzle_02_scaling_model_results_v1.4.json'
    target.write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__': main()
