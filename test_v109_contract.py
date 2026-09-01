#!/usr/bin/env python3
from pathlib import Path

V108=Path('3dprint_black_mirror_wave_grid_v1.108.py')
V109=Path('3dprint_black_mirror_wave_grid_v1.109.py')

def must(v,msg):
    if not v: raise AssertionError(msg)

def main():
    must(V108.exists(),'v1.108 failed upper-arc predecessor missing')
    must(V109.exists(),'v1.109 closed-global wrapper missing (expected RED before implementation)')
    s=V109.read_text(encoding='utf-8')
    for token in ('3dprint_black_mirror_wave_grid_v1.109','REAR_VERSION_TEXT = "109"',
                  'CLOSED_GLOBAL_WAVESET','closed_equal_optical_path_contour',
                  'GLOBAL_WAVESET_START_MM = 0.600','GLOBAL_WAVESET_ZERO_GAP_MM = 0.400',
                  'FC3D_V1109_U_PROFILE_SEG','direct_xyz'):
        must(token in s,f'missing v1.109 contract token: {token}')
    print('PASS: v1.109 closed global wave-set source contract present')

if __name__=='__main__': main()
