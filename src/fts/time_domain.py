from __future__ import annotations

from typing import Optional


def normalize_gdf_time_domain(value: object) -> Optional[str]:
    """Return a conservative OSM conditional time expression placeholder.

    TODO:
        Implement full GDF time domain parsing for your internal RULE_TIME and
        EXPECTIME encoding. Until that parser is available, this function preserves
        the source expression and makes the conditional tag traceable, but it should
        not be considered a fully standards-compliant OSM opening_hours expression.
    """
    if value is None:
        return None
    text = str(value).strip()
    if not text or text in {"0", "0000000000000000"}:
        return None
    return text


def conditional_no(time_value: object) -> Optional[str]:
    expr = normalize_gdf_time_domain(time_value)
    if not expr:
        return None
    return f"no @ ({expr})"


def conditional_restriction(restriction: str, time_value: object) -> Optional[str]:
    expr = normalize_gdf_time_domain(time_value)
    if not expr:
        return None
    return f"{restriction} @ ({expr})"
