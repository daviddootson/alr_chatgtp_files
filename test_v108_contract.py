#!/usr/bin/env python3
from pathlib import Path

V107 = Path('3dprint_black_mirror_wave_grid_v1.107.py')
V108 = Path('3dprint_black_mirror_wave_grid_v1.108.py')

def must(cond, msg):
    if not cond:
        raise AssertionError(msg)

def main():
    must(V107.exists(), 'v1.107 diagnostic predecessor missing')
    old = V107.read_text(encoding='utf-8')
    must('continuous_long_u_profile_direct_xyz' in old, 'v1.107 direction-correct topology marker missing')
    must(V108.exists(), 'v1.108 production wrapper is missing (expected RED before implementation)')
    src = V108.read_text(encoding='utf-8')
    for token in (
        '3dprint_black_mirror_wave_grid_v1.108',
        'REAR_VERSION_TEXT = "108"',
        'GLOBAL_WAVESET',
        'global_wave_set_schedule',
        'FC3D_V1108_U_PROFILE_SEG',
        'direct_xyz',
        '0.600',
        '0.400',
    ):
        must(token in src, f'v1.108 required token missing: {token}')
    must('coupon_local_reseed' not in src, 'v1.108 must not reseed wave sets from a clipped coupon contour')
    print('PASS: v1.108 global wave-set source contract present')

if __name__ == '__main__':
    main()
