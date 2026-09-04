#!/usr/bin/env python3
from pathlib import Path

V109=Path('3dprint_black_mirror_wave_grid_v1.109.py')
V110=Path('3dprint_black_mirror_wave_grid_v1.110.py')

def must(v,msg):
    if not v: raise AssertionError(msg)

def main():
    must(V109.exists(),'v1.109 closed-global predecessor missing')
    must(V110.exists(),'v1.110 sparse-global wrapper missing (expected RED before implementation)')
    s=V110.read_text(encoding='utf-8')
    for token in (
        '3dprint_black_mirror_wave_grid_v1.110',
        'REAR_VERSION_TEXT = "110"',
        'SPARSE_GLOBAL_METRIC',
        'SPARSE_METRIC_SAMPLES',
        'GLOBAL_WAVESET_START_MM = 0.600',
        'GLOBAL_WAVESET_ZERO_GAP_MM = 0.400',
        'scaled_sparse_spacing',
        'FC3D_V1110_U_PROFILE_SEG',
        'direct_xyz',
    ):
        must(token in s,f'missing v1.110 contract token: {token}')
    print('PASS: v1.110 sparse-global source contract present')

if __name__=='__main__': main()
