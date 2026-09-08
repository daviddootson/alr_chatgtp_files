import importlib.util, sys, math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('study',HERE/'ALR_thincap_wwk_v1_0.py')
study=importlib.util.module_from_spec(spec);sys.modules[spec.name]=study;spec.loader.exec_module(study)
geo=study.geo

def centre(): return geo.card_points('1-2',3)[4]

def test_full_cap_reproduces_standard_stack():
    c=centre();dose=.24;scale=1.2
    b1,r1,_=geo.stack(c,'WWK',dose,scale,0)
    b2,r2=study.stack_variable(c,dose,dose,scale,0)
    assert np.allclose(b1,b2,atol=1e-12)
    assert np.allclose(r1[:,:4],r2[:,:4],atol=1e-12)

def test_white_geometry_does_not_change_with_cap_height():
    c=centre();a=study.white_samples_variable(c,.24,.24,1.2,0,128)
    b=study.white_samples_variable(c,.24,.10,1.2,0,128)
    for x,y in zip(a,b): assert np.allclose(x,y,atol=1e-12)

def test_top_cap_base_position_is_unchanged_by_cap_height():
    c=centre();_,a=study.stack_variable(c,.24,.24,1.2,0)
    _,b=study.stack_variable(c,.24,.10,1.2,0)
    ta=a[a[:,2]==2][0];tb=b[b[:,2]==2][0]
    assert math.isclose(ta[0],tb[0],abs_tol=1e-12)
    assert math.isclose(ta[1],tb[1],abs_tol=1e-12)

def test_thin_cap_reduces_total_silhouette_height():
    assert study.total_height(.24,.10,1.2) < study.total_height(.24,.24,1.2)
    assert math.isclose(study.total_height(.24,.10,1.2),(.24+.24+.10)*1.2,abs_tol=1e-12)

def test_full_cap_pitch_matches_standard_wwk():
    c=centre();p0=geo.solve_pitch(c,'WWK',.24,1.2,60,0,0,'white')
    p1=study.solve_pitch_variable(c,.24,.24,1.2,60,0,0)
    assert abs(p0-p1)<2e-4

def test_thin_cap_does_not_increase_minimum_pitch_at_same_visibility():
    c=centre();full=study.solve_pitch_variable(c,.24,.24,1.2,60,0,0)
    thin=study.solve_pitch_variable(c,.24,.10,1.2,60,0,0)
    assert thin <= full+1e-8

if __name__=='__main__':
    tests=[v for k,v in sorted(globals().items()) if k.startswith('test_')]
    for t in tests:t();print('PASS',t.__name__)
