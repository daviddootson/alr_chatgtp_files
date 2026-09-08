# v1.158 thin-cap executable-Z fix

Date: 8 September 2026.

## Why v1.158 exists

Direct audit of `ALR_WWK_1-2_V50_L0p22_S1p2_H0_C0p1_v157.gcode.3mf` found a print-stopping v1.157 bug. The tier-3 cap road marker and descent were Z1.048, but the executable `SUPPORT_SEG` and `SUPPORT_DRY_TAIL` moves remained at the old full-height v156 top Z1.192. Do not print that v1.157 package.

## v1.158 behavior

v1.158 keeps the same thin-cap model and CLI, but when the top-K cap is active it now rewrites the executable cap segment and dry-tail Z words to the true cap top as well as the marker/descent. It also adds a fail-closed audit of the actual executable tier Z values and cap E/mm before the inherited v1.156 audit is normalized.

The project-settings startup/end revision markers are also rewritten from V1156 to V1158 so the packaged metadata is version-consistent.

Target command remains:

```cmd
py 3dprint_black_mirror_wave_grid_v1.158.py --source 3dprintv1.179.py --piece 1-2 --layer-map wwk --layer-height-mm 0.22 --cap-height-mm 0.10 --physical-height-scale 1.2 --visibility-percent 50 --horizontal-percent 0 --slicer-target orca
```

Expected tier tops above the 0.400 mm base are Z0.664, Z0.928 and Z1.048. Expected cap draw dose is 0.01567 mm filament per mm of road.

## Verification

- Reproduced the v1.157 failure with a regression test.
- v1.158 synthetic thin-cap regression checks: 5/5 PASS.
- Revision/project-settings/MD5 postprocess test: PASS.
- Python compilation: PASS.
- The new actual-cap audit rejects the uploaded v1.157 G-code and passes the same real optical block after correcting only the cap executable Z words; on that real block it saw 282/188/94 tier roads and 8,821 cap extrusion segments, with mean cap E/mm 0.0156700333.

The full generated v1.158 package still needs to be regenerated from the converter and audited before physical printing.
