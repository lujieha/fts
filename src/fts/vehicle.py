from __future__ import annotations

from typing import Dict, Optional


VEHICLE_TAG_ORDER = [
    "motorcar",
    "hgv",
    "bus",
    "taxi",
    "motorcycle",
    "goods",
    "hazmat",
    "emergency",
]


def decode_vehicle_mask(vehicle: object) -> Dict[str, str]:
    """Decode source VEHICLE mask into OSM access tags.

    TODO:
        Replace this conservative placeholder with the exact bit layout from your
        data production specification. The current behavior only detects the common
        all-zero forbidden value and otherwise preserves the mask in source tags.
    """
    if vehicle is None:
        return {}
    text = str(vehicle).strip()
    if not text:
        return {}
    if set(text) <= {"0"}:
        return {"motor_vehicle": "no", "source:vehicle_mask": text}
    return {"motor_vehicle": "yes", "source:vehicle_mask": text}


def apply_vehicle_restriction(tags: Dict[str, str], vehicle: Optional[str]) -> Dict[str, str]:
    if not vehicle:
        return tags
    out = dict(tags)
    decoded = decode_vehicle_mask(vehicle)
    out.update(decoded)
    return out
