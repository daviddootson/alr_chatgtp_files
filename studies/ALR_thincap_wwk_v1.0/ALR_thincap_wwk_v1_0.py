#!/usr/bin/env python3
"""Thin-cap WWK local optical prediction v1.0.

Analysis only; not printer G-code. Uses the reconstructed v156 mapped-white
spacing/scoring model and the v1.2 central PETG material assumptions.
The two W tiers retain normal WWK geometry. Only the top K bead height changes.
"""
from __future__ import annotations
import importlib.util, sys, math, json, argparse, time
from pathlib import Path
import numpy as np

VERSION='1.0'
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('matv12',HERE/'material_model_v1_2.py')
mat=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mat;spec.loader.exec_module(mat)
geo=mat.geo
COUNTS=(3,2,1)
MAPPING='WWK'

def tier_heights(w_dose,k_dose,scale):
    return np.array([w_dose*scale,w_dose*scale,k_dose*scale],float)

def tier_bases(w_dose,k_dose,scale):
    h=tier_heights(w_dose,k_dose,scale)
    return np.array([0.,h[0],h[0]+h[1]],float)

def total_height(w_dose,k_dose,scale):
    return float(np.sum(tier_heights(w_dose,k_dose,scale)))

def stack_variable(c,w_dose,k_dose,scale,H):
    """WWK counts 3-2-1. Tier base shifts follow cumulative height/tan(tilt).

    The top K base therefore stays exactly where normal WWK puts it when W
    height is unchanged; only the K bead's own vertical height changes.
    """
    b,p,v,tilt=geo.frame(c,H);bases=tier_bases(w_dose,k_dose,scale)
    shifts=bases/np.tan(tilt);rows=[]
    for t,count in enumerate(COUNTS):
        for i in range(count):rows.append((shifts[t]+(i+.5)*.4,bases[t],t,i,tier_heights(w_dose,k_dose,scale)[t]))
    return b,np.array(rows,float)

def white_samples_variable(c,w_dose,k_dose,scale,H,count=256):
    b,roads=stack_variable(c,w_dose,k_dose,scale,H);a=.2
    # Both working tiers remain full W height, so cap height must not affect them.
    h=w_dose*scale
    phi=(np.arange(count)+.5)*np.pi/(2*count);co=np.cos(phi);si=np.sin(phi)
    w=np.hypot(a*si,h*co)*np.pi/(2*count);norm=np.hypot(h*co,a*si)
    points=[];normals=[];weights=[];ids=[]
    for t in (0,1):
        row=roads[roads[:,2]==t];uc=float(row[-1,0]);base=float(row[-1,1])
        u=uc+a*co
        points.append(np.column_stack([c[0]+b[0]*u,c[1]+b[1]*u,base+h*si]))
        normals.append(np.column_stack([b[0]*h*co/norm,b[1]*h*co/norm,a*si/norm]))
        weights.append(w);ids.extend([t]*count)
    return np.concatenate(points),np.concatenate(normals),np.concatenate(weights),np.array(ids)

def white_ray_mask_variable(points,normals,c,w_dose,k_dose,scale,H,target=geo.PROJECTOR):
    b,roads=stack_variable(c,w_dose,k_dose,scale,H)
    ray=target-points;dist=np.linalg.norm(ray,axis=1);ray/=dist[:,None]
    facing=np.sum(normals*ray,axis=1)>0
    q0=((points[:,:2]-c)@b)[:,None];dq=(ray[:,:2]@b)[:,None]
    rh=ray[:,2,None];h0=points[:,2,None];a=.2
    uc=roads[:,0][None,:];base=roads[:,1][None,:];hh=roads[:,4][None,:]
    lo=np.maximum(1e-5,(base-h0)/rh);hi=np.minimum(dist[:,None],(base+hh-h0)/rh)
    v0=h0-base;aa=(dq/a)**2+(rh/hh)**2
    bb=2*((q0-uc)*dq/a**2+v0*rh/hh**2);cc=((q0-uc)/a)**2+(v0/hh)**2-1
    t=np.maximum(lo,np.minimum(hi,-bb/(2*aa)))
    blocked=np.any((hi>lo)&((aa*t*t+bb*t+cc)<-1e-8),axis=1)
    return facing&~blocked

def physical_gap(c,c1,w_dose,k_dose,scale,H):
    """Approximate v156 physical envelope gap for same corresponding tiers."""
    _,r0=stack_variable(c,w_dose,k_dose,scale,H);_,r1=stack_variable(c1,w_dose,k_dose,scale,H)
    d=float(np.linalg.norm(c1-c));g=[]
    for t,count in enumerate(COUNTS):
        a=r0[r0[:,2]==t];b=r1[r1[:,2]==t]
        # left/right extent shifts are represented by leading-road centre shift;
        # all beads retain 0.4-mm width.
        shift=float(b[-1,0]-a[-1,0]);g.append(d+shift-count*.4)
    return min(g)

def pitch_valid_variable(c,w_dose,k_dose,scale,V,H,pitch):
    samples=white_samples_variable(c,w_dose,k_dose,scale,H)
    own=white_ray_mask_variable(samples[0],samples[1],c,w_dose,k_dose,scale,H)
    if geo.white_fraction(samples,own)<V/100-1e-9:return False
    c1=geo.advance(c,pitch,H)
    if physical_gap(c,c1,w_dose,k_dose,scale,H)<-1e-12:return False
    mask=own&white_ray_mask_variable(samples[0],samples[1],c1,w_dose,k_dose,scale,H)
    return geo.white_fraction(samples,mask)>=V/100-1e-9

def physically_valid_variable(c,w_dose,k_dose,scale,H,pitch):
    return physical_gap(c,geo.advance(c,pitch,H),w_dose,k_dose,scale,H)>=-1e-12

def actual_white_fraction(c,w_dose,k_dose,scale,H,pitch):
    samples=white_samples_variable(c,w_dose,k_dose,scale,H)
    own=white_ray_mask_variable(samples[0],samples[1],c,w_dose,k_dose,scale,H)
    c1=geo.advance(c,pitch,H)
    mask=own&white_ray_mask_variable(samples[0],samples[1],c1,w_dose,k_dose,scale,H)
    return geo.white_fraction(samples,mask)

def solve_pitch_variable(c,w_dose,k_dose,scale,V,H,floor=0.):
    # A 3-road bottom tier imposes a 1.2-mm physical floor before local shifts.
    lo=max(float(floor),1.2)
    if pitch_valid_variable(c,w_dose,k_dose,scale,V,H,lo):return lo
    hi=max(lo,.45)
    for _ in range(90):
        hi*=1.12
        if pitch_valid_variable(c,w_dose,k_dose,scale,V,H,hi):break
        if hi>8:return np.nan
    for _ in range(32):
        mid=(lo+hi)/2
        if pitch_valid_variable(c,w_dose,k_dose,scale,V,H,mid):hi=mid
        else:lo=mid
    return hi

def polygons_variable(c,w_dose,k_dose,scale,H,segments=64):
    b,roads=stack_variable(c,w_dose,k_dose,scale,H);power=geo.volume_power(scale);a=.2
    theta=np.linspace(np.pi,0,segments+1);xx=a*np.sign(np.cos(theta))*np.abs(np.cos(theta))**(2/power)
    shapes=[];colours=[]
    for uc,base,t,i,h in roads:
        zz=h*np.sin(theta)**(2/power);shapes.append(np.column_stack([uc+xx,base+zz]))
        t=int(t);i=int(i);colours.append(1. if t in (0,1) and i==COUNTS[t]-1 else .025)
    return np.array(shapes),np.array(colours)

def geometry_kernel_variable(c,w_dose,k_dose,scale,H,pitch,offset,nrays,segments,nambient):
    b,p,_,_=geo.frame(c,H);a=np.array([-b[1],b[0]])
    polygons,colours=polygons_variable(c,w_dose,k_dose,scale,H,segments)
    sources=np.vstack([p,mat.source_directions(nambient)])
    lights=np.column_stack([sources[:,:2]@b,sources[:,:2]@a,sources[:,2]])
    target=geo.VIEWER+np.array([offset,0.,0.]);v=geo.unit(target-np.r_[c,0.]);local_v=np.array([v[:2]@b,v[:2]@a,v[2]])
    hits=geo.first_hits(polygons,colours,pitch,local_v[0]/local_v[2],nrays)
    normals,index=np.unique(np.round(np.column_stack([hits[2],hits[3]]),13),axis=0,return_inverse=True)
    kernel,lit=mat.collect_kernel(polygons,pitch,hits,lights,index,len(normals))
    gap=geo.longest_dark_fraction(lit)*pitch/np.sqrt(1+(local_v[0]/local_v[2])**2)
    return dict(kernel=kernel,normals=normals,lights=lights,viewer=local_v,lit_white_fraction=float(lit.mean()),dark_band_mm=float(gap))

def prepare_petg_central():
    # Same central PETG surface as v1.2 (eta=1.57, alpha=.22), but only one surface.
    table,average=mat.energy_table(1.57,.22)
    return np.array([1.57]),np.array([.22]),np.array([table]),np.array([average])

def response(coeff,rw=.75,rk=.025):
    a=np.asarray(coeff)
    # coeff dims surface, colour K/W, source, spec/diff-unit
    return a[0,1,:,0]+rw*a[0,1,:,1]+a[0,0,:,0]+rk*a[0,0,:,1]

def score_reference(rays=768,segments=80,ambient=384,grid=3):
    material=prepare_petg_central();vals=[];records=[]
    points=geo.card_points('1-2',3)[4:5] if grid==1 else geo.card_points('1-2',grid)
    for c in points:
        pitch=geo.solve_pitch(c,'KWK',.20,1.2,70,0,0,'white')
        for off in (-1000.,0.,1000.):
            g=mat.geometry_kernel(c,dict(layer_map='KWK',layer_height_mm=.20,physical_height_scale=1.2,horizontal_percent=0),pitch,off,rays,segments,ambient)
            coeff=mat.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
            vals.append(response(coeff));records.append((pitch,g['dark_band_mm'],g['lit_white_fraction']))
    arr=np.array(vals);return arr.mean(axis=0),records

def score_case(w_dose,k_dose,V,pitch_offset=0.,rays=768,segments=80,ambient=384,grid=3):
    material=prepare_petg_central();vals=[];records=[];target_met=[];physical=[]
    points=geo.card_points('1-2',3)[4:5] if grid==1 else geo.card_points('1-2',grid)
    for c in points:
        auto=solve_pitch_variable(c,w_dose,k_dose,1.2,V,0,0)
        pitch=auto+pitch_offset
        pv=physically_valid_variable(c,w_dose,k_dose,1.2,0,pitch);physical.append(pv)
        if not pv:continue
        frac=actual_white_fraction(c,w_dose,k_dose,1.2,0,pitch);target_met.append(frac>=V/100-1e-9)
        for off in (-1000.,0.,1000.):
            g=geometry_kernel_variable(c,w_dose,k_dose,1.2,0,pitch,off,rays,segments,ambient)
            coeff=mat.compute_coefficients(g['kernel'],g['normals'],g['lights'],g['viewer'],*material,ambient)
            vals.append(response(coeff));records.append(dict(pitch_mm=float(pitch),auto_pitch_mm=float(auto),offset_mm=off,dark_band_mm=g['dark_band_mm'],lit_white_fraction=g['lit_white_fraction'],actual_target_white_fraction=float(frac)))
    if not vals:return None
    return dict(response=np.array(vals).mean(axis=0),records=records,physical_all=all(physical),target_met_all=all(target_met))

def main():
    p=argparse.ArgumentParser();p.add_argument('--quick',action='store_true');a=p.parse_args()
    print('Thin-cap WWK model loaded. Use sweep_thincap_wwk_v1_0.py for the full study.')
if __name__=='__main__':main()
