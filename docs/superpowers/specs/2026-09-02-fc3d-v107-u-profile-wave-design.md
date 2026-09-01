# FC3D v1.107 Correct U-Profile Wave Design

## Status

Approved design for the successor to rejected v1.106. v1.106 remains immutable and must not be printed.

## Goal

Replace only the Layer-4 wave topology so the actual extrusion roads form the wave cross-section along the local projector/viewer bisecting-normal direction, while preserving the validated A1 Mini support, 25% valley fill, pressure mechanics, package metadata and rear marking conventions.

## Optical frame

At every sampled screen point, `mirror_frame_global()` is authoritative.

- `+u` is `b_unit`: inward/toward projector in the screen plane.
- `-u` is outward/away from projector.
- `a_unit` is the transverse/around-arc tangent.
- The required 3D optical surface normal is `normal_unit`.

No global radial approximation and no fixed optical angle may replace this local frame.

## Primitive print road

The primitive emitted road is one complete local u-profile, not a constant-height contour:

1. valley lead: `+u`, h=0, nominal XY run 0.100 mm;
2. optical front: `-u,+h`, total rise 0.250 mm, integrated from the exact local bisecting-normal tilt;
3. hidden upper/rear slope: `+u,+h`, nominal XY run 0.400 mm, additional rise 0.050 mm;
4. return: `+u,-h`, descend from h=0.300 to h=0 with nominal return angle retained from the wave experiment unless visibility/closure audit proves invalid.

Maximum wave relief is exactly 0.300 mm above the valley. Wave-forming extrusion feed is 50 mm/s (F3000). Extrusion is calculated from intended true 3D segment length.

Because the A1 representation deliberately keeps the logical G1 Z constant, the physical height profile is represented with fine G29.1 offset steps along the u-profile. Direct G1 Z must remain at the single optical logical layer value so Studio/Orca do not fragment the optical layer.

## Around-arc sampling and wave sets

Neighbouring primitive u-profile roads are sampled around the transverse contour. The sample count is fixed for the lifetime of one wave set so those roads converge naturally as the successive inward contours shrink.

For each new set:

- begin outer-to-inner;
- choose an integer number of around-arc intervals that gives a start centre spacing at least 0.600 mm and as close to 0.600 mm as possible; this is a nominal 0.200 mm clear gap between 0.400 mm roads;
- retain the same normalized around-arc sample positions while advancing successive complete wave cells inward;
- measure the actual adjacent-road spacing on each newly reached valley contour;
- when the minimum spacing reaches about 0.400 mm (zero nominal gap), finish that entire wave cell/arc, end the set, and start the next set from that inward contour with fewer around-arc roads so start spacing returns to about 0.600 mm;
- never delete a road or reset the sampling partway around an arc.

Thus road count is constant inside a set and decreases only at complete-set boundaries.

## Pressure and support mechanics retained

- top support/base: 0.20 X, +0.10 Y, +0.10 X; support top Z0.400;
- 25% midpoint valley fill at effective Z0.420 via G29.1, E/mm 0.0039175;
- optical reprime +0.795 mm;
- optical retract -0.800 mm;
- moving dry tail 0.160 mm;
- pressure-only feed F1800;
- endpoint trim 0 unless explicitly requested.

One pressure cycle is owned by each complete emitted u-profile road. The dry tail is taken from the final portion of that road without changing its geometry.

## Direction/orientation audit

Every positive-E u-profile segment is audited from its actual emitted XY endpoints against `mirror_frame_global()` at the segment midpoint.

- valley lead: dot(direction, +u) positive and near 1; height change approximately zero;
- optical front: dot(direction, +u) negative and near -1; height increases;
- hidden top: dot(direction, +u) positive and near 1; height increases only to the 0.300-mm cap;
- return: dot(direction, +u) positive and near 1; height decreases to valley.

The audit must also report alignment with `a_unit`; a build dominated by transverse/tangential extrusion must fail. Optical-front surface-normal error and hidden-surface projector clearance remain independently audited.

## Version and release contract

The changed wrapper is `3dprint_black_mirror_wave_grid_v1.107.py`. Filename, `SCRIPT_VERSION`, markers, reports, rear version `107`, default output names and sample commands must all say v1.107. v1.106 is only the predecessor/RED reference.

Release requires: source regression, dry validation against real `3dprintv1.179.py`, Orca package generation and independent audit, Studio generation and independent audit, Orca/Studio executable comparison, then human Layer-4 slicer preview. No novel v1.107 geometry is called print-ready before that visual preview.