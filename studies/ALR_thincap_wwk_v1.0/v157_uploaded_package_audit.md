# v1.157 uploaded package audit

File: `ALR_WWK_1-2_V50_L0p22_S1p2_H0_C0p1_v157.gcode.3mf`

## Verdict

**FAIL — do not print this v1.157 package.**

The archive is structurally valid and its stored G-code MD5 matches. The embedded v157 audits report PASS, the mapped spacing report is internally consistent, the colour sequence is `[black, white, black]`, and the intended cap is recorded as 0.10 mm dose / 0.12 mm physical height.

However, direct executable-G-code inspection found a print-stopping mismatch:

- tier 3 road marker: **Z1.048**
- tier 3 descent: **Z1.048**
- tier 3 actual extrusion segments: **Z1.192**
- tier 3 dry tails: **Z1.192**

So the executable cap is still emitted at the old full-height v156 top. The first cap extrusion move rises by 0.144 mm from the declared cap height.

## Other checks

- ZIP integrity: PASS
- plate_1.gcode MD5: PASS
- 564 optical support roads: PASS
- tier road counts: 3/2/1 per stack, 94 stacks
- mapped-white spacing: PASS in embedded report
- mean pitch: 1.676327 mm
- minimum physical gap: 0.389345 mm
- minimum projector-visible white fraction: 0.500101
- cap E/mm: embedded audit 0.01567 mm filament per mm road
- project settings retain V1156 startup/end markers: low-severity metadata inconsistency

## Corrective action

Use **v1.158 or later**. v1.158 patches the executable cap `SUPPORT_SEG` and `SUPPORT_DRY_TAIL` Z words as well as the road marker/descent, and adds a fail-closed audit of actual tier Z and cap E/mm.
