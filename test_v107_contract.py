#!/usr/bin/env python3
"""Source-level RED/GREEN contract for FC3D v1.107.

The previous v1.106 is deliberately expected to exhibit the rejected full-contour
wave topology. The successor must advertise and implement the u-profile topology
before expensive full-package validation is attempted.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
V106 = ROOT / "3dprint_black_mirror_wave_grid_v1.106.py"
V107 = ROOT / "3dprint_black_mirror_wave_grid_v1.107.py"
EXPECTED_V106_SHA256 = "a7e14bf818033aff390f69fd0e27368a8917a8a60dbb9c29c5d1a5c308814e80"


def must(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    must(V106.exists(), f"missing predecessor: {V106.name}")
    v106_bytes = V106.read_bytes()
    sha = hashlib.sha256(v106_bytes).hexdigest()
    must(sha == EXPECTED_V106_SHA256, f"v1.106 SHA-256 changed: {sha}")
    v106 = v106_bytes.decode("utf-8")

    # RED evidence: the predecessor genuinely contains the rejected topology.
    must("FC3D_V1106_WAVE_ARC" in v106, "v1.106 no longer exhibits the rejected WAVE_ARC topology")
    must('("VALLEY",current,0.0)' in v106 and '("OPTICAL_CREST",crest,WAVESET_OPTICAL_RISE_MM)' in v106,
         "v1.106 five-contour construction signature changed")

    # This is the intended RED failure before production code exists.
    must(V107.exists(), "v1.107 production wrapper is missing (expected RED before implementation)")
    v107 = V107.read_text(encoding="utf-8")

    must('SCRIPT_VERSION = "3dprint_black_mirror_wave_grid_v1.107"' in v107,
         "v1.107 SCRIPT_VERSION missing")
    must('REAR_VERSION_TEXT = "107"' in v107 or 'REAR_VERSION_TEXT = \\"107\\"' in v107,
         "v1.107 rear version 107 not established")
    must("FC3D_V1107_U_PROFILE_SEG" in v107, "v1.107 u-profile segment marker missing")
    must("generate_u_profile_wave_sets" in v107, "v1.107 u-profile wave-set generator missing")
    must("audit_u_profile_orientation" in v107, "v1.107 local-u orientation audit missing")
    must("WAVESET_RESET_CENTER_SPACING_MM" in v107 and "WAVESET_MIN_CENTER_SPACING_MM" in v107,
         "v1.107 spacing contract constants missing")
    must("EXPECTED_V106_SHA256" in v107, "v1.107 does not fail closed on exact predecessor")

    # The v1.107 source may mention the old marker only as a forbidden/regression
    # token; it must not itself emit an active WAVE_ARC command.
    active_old_emission = re.findall(r'rows\.append\([^\n]*FC3D_V1106_WAVE_ARC', v107)
    must(not active_old_emission, f"v1.107 still actively emits old WAVE_ARC topology: {active_old_emission[:2]}")

    print("PASS: v1.106 rejected topology reproduced; v1.107 u-profile source contract present")


if __name__ == "__main__":
    main()
