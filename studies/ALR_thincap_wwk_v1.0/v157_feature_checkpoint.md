# v1.157 thin-cap converter checkpoint

Status: implementation verified locally on 8 September 2026.

The new converter is `3dprint_black_mirror_wave_grid_v1.157.py`. It adds `--cap-height-mm`, which changes only the final/top K tier material-dose height. All lower tiers retain v1.156 geometry and dose. The cap physical height is `cap-height-mm * physical-height-scale`; its base/XY registration is unchanged, while blocker height, cap draw E, top Z, tower schedule, rear marking and audit metadata use the cap value.

Target physical test:

```cmd
py 3dprint_black_mirror_wave_grid_v1.157.py --source 3dprintv1.179.py --piece 1-2 --layer-map wwk --layer-height-mm 0.22 --cap-height-mm 0.10 --physical-height-scale 1.2 --visibility-percent 50 --horizontal-percent 0 --slicer-target orca
```

Expected tier physical heights for this command: W=0.264 mm, W=0.264 mm, K=0.120 mm; support top Z above a 0.400-mm base is 1.048 mm. The earlier local optical study predicted this W0.22/K0.10/V50 family at about 1.676-mm pitch, ~1.216-mm viewer dark band, ~134.8 brightness index and ~100.6 contrast index against the current PETG KWK/v156 baseline. Those remain model predictions, not physical measurements.

Local verification before publication: 8 pytest checks passed; Python compilation passed. The remote converter was fetched back and its Git blob SHA matched the locally verified canonical copy. Canonical converter SHA-256: `22e1b5d54b8c3dc6dd53ce8ceba0e628b3a835deda2ea263f6f0cd382218be7c`. No published file exceeds 50 MB.

Important dependency: v1.157 is a bounded compatibility wrapper and requires `3dprint_black_mirror_wave_grid_v1.156.py` beside it. v1.156 remains unchanged.
