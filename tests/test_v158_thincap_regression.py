import importlib.util
from pathlib import Path
from types import SimpleNamespace

TARGET = Path(__file__).resolve().parent.parent / '3dprint_black_mirror_wave_grid_v1.158.py'


def load_target():
    spec = importlib.util.spec_from_file_location('v158', TARGET)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def runtime(cap=0.10):
    return SimpleNamespace(
        LAYER_MAP='WWK', LAYER_HEIGHT_MM=0.22, PHYSICAL_HEIGHT_SCALE=1.2,
        PHYSICAL_LAYER_HEIGHT_MM=0.264, BASE_TOP_Z_MM=0.4,
        A_MAIN_E_PER_MM=0.1567*0.22,
        TIER_TOP_Z_MM=(0.664,0.928,0.928+cap*1.2),
    )


def sample_rows():
    return [
        '; FC3D_V1156_OPTICAL_START mode=mapped-pyramid',
        '; FC3D_V1156_SUPPORT_ROAD_START road=1 stack=1 tier=1 tier_road=1 z=0.664',
        'G0 X10.000 Y10.000 F18000 ; FC3D_V1156_SUPPORT_MOVE',
        'G0 Z0.664 F900 ; FC3D_V1156_SUPPORT_HEIGHT',
        'G1 X11.000 Y10.000 Z0.664 E0.034474 F15000 ; FC3D_V1156_SUPPORT_SEG road=1 seg=0',
        'G1 X11.160 Y10.000 Z0.664 F15000 ; FC3D_V1156_SUPPORT_DRY_TAIL len=0.160',
        '; FC3D_V1156_SUPPORT_ROAD_END road=1',
        '; FC3D_V1156_SUPPORT_ROAD_START road=2 stack=1 tier=2 tier_road=1 z=0.928',
        'G0 X10.000 Y11.000 F18000 ; FC3D_V1156_SUPPORT_MOVE',
        'G0 Z0.928 F900 ; FC3D_V1156_SUPPORT_HEIGHT',
        'G1 X11.000 Y11.000 Z0.928 E0.034474 F15000 ; FC3D_V1156_SUPPORT_SEG road=2 seg=0',
        'G1 X11.160 Y11.000 Z0.928 F15000 ; FC3D_V1156_SUPPORT_DRY_TAIL len=0.160',
        '; FC3D_V1156_SUPPORT_ROAD_END road=2',
        '; FC3D_V1156_SUPPORT_ROAD_START road=3 stack=1 tier=3 tier_road=1 z=1.192',
        'G0 Z1.352 F900 ; FC3D_V1156_SUPPORT_TRAVEL_Z',
        'G0 X10.000 Y12.000 F18000 ; FC3D_V1156_SUPPORT_MOVE',
        'G0 Z1.192 F900 ; FC3D_V1156_SUPPORT_HEIGHT',
        'G1 E0.795 F1800 ; FC3D_V1156_SUPPORT_REPRIME',
        'G1 X11.000 Y12.000 Z1.192 E0.034474 F15000 ; FC3D_V1156_SUPPORT_SEG road=3 seg=0',
        'G1 E-0.800 F1800 ; FC3D_V1156_SUPPORT_RETRACT',
        'G1 X11.160 Y12.000 Z1.192 F15000 ; FC3D_V1156_SUPPORT_DRY_TAIL len=0.160',
        '; FC3D_V1156_SUPPORT_ROAD_END road=3',
    ]


def patched_base():
    mod=load_target()
    return mod, mod._install(mod._load_v157())


def test_thin_cap_rewrites_executable_segment_and_tail_z():
    mod,base=patched_base(); rt=runtime(0.10)
    text='\n'.join(base._patch_emitted_rows(sample_rows(),rt,0.10))
    assert 'tier=3 tier_road=1 z=1.048' in text
    assert 'G0 Z1.048 F900 ; FC3D_V1156_SUPPORT_HEIGHT' in text
    assert 'G1 X11.000 Y12.000 Z1.048 E0.01567 ' in text
    assert 'G1 X11.160 Y12.000 Z1.048 F15000 ; FC3D_V1156_SUPPORT_DRY_TAIL' in text


def test_full_height_cap_reproduces_v156_top_z_and_dose():
    mod,base=patched_base(); rt=runtime(0.22)
    text='\n'.join(base._patch_emitted_rows(sample_rows(),rt,0.22))
    assert 'tier=3 tier_road=1 z=1.192' in text
    assert 'Z1.192 E0.034474 ' in text


def test_actual_cap_audit_rejects_v157_style_executable_z():
    mod=load_target(); rt=runtime(0.10)
    try:
        mod._audit_actual_cap_block('\n'.join(sample_rows()),rt,0.10)
    except RuntimeError:
        return
    raise AssertionError('v1.157-style cap Z mismatch was not rejected')


def test_actual_cap_audit_accepts_corrected_rows():
    mod,base=patched_base(); rt=runtime(0.10)
    fixed='\n'.join(base._patch_emitted_rows(sample_rows(),rt,0.10))
    result=mod._audit_actual_cap_block(fixed,rt,0.10)
    assert result['status']=='PASS'
    assert result['tier_top_z_mm']==[0.664,0.928,1.048]
    assert abs(result['cap_draw_e_per_mm']-0.01567)<8e-5
