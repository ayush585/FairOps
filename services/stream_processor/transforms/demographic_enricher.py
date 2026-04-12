"""
Stream Processor Transform — Demographic Enrichment.

Maps raw feature values to standardized demographic tags.
Sprint 1: Direct label mapping only (no proxy mode).

Ref: AGENT.md Section 8.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Optional

import apache_beam as beam

logger = logging.getLogger("fairops.stream_processor.demographic_enricher")


# ── Lookup Dictionaries (AGENT.md Section 8) ─────────────────────────────────

GENDER_MAP = {
    "M": "MALE",
    "F": "FEMALE",
    "male": "MALE",
    "female": "FEMALE",
    "Male": "MALE",
    "Female": "FEMALE",
    "0": "MALE",
    "1": "FEMALE",
    "m": "MALE",
    "f": "FEMALE",
}

AGE_BINS = [
    (0, 18, "AGE_UNDER_18"),
    (18, 30, "AGE_18_30"),
    (30, 40, "AGE_30_40"),
    (40, 50, "AGE_40_50"),
    (50, 60, "AGE_50_60"),
    (60, 999, "AGE_60_PLUS"),
]

RACE_MAP = {
    "White": "WHITE",
    "Black": "BLACK",
    "Asian-Pac-Islander": "ASIAN_PACIFIC",
    "Amer-Indian-Eskimo": "NATIVE_AMERICAN",
    "Other": "OTHER",
    "white": "WHITE",
    "black": "BLACK",
    "asian": "ASIAN_PACIFIC",
    "hispanic": "HISPANIC",
}


def _classify_age(age_value) -> Optional[str]:
    """Classify an age value into a bin."""
    try:
        age = int(float(age_value))
        for low, high, label in AGE_BINS:
            if low <= age < high:
                return label
    except (ValueError, TypeError):
        pass
    return None


def _map_gender(gender_value) -> Optional[dict]:
    """Map a gender value to a distribution dict."""
    if gender_value is None:
        return None

    gender_str = str(gender_value).strip()
    mapped = GENDER_MAP.get(gender_str)

    if mapped:
        # Direct label → 100% confidence distribution
        return {mapped: 1.0}
    return None


def _map_race(race_value) -> Optional[dict]:
    """Map a race value to a distribution dict."""
    if race_value is None:
        return None

    race_str = str(race_value).strip()
    mapped = RACE_MAP.get(race_str)

    if mapped:
        return {mapped: 1.0}
    return None


class EnrichDemographics(beam.DoFn):
    """
    Enriches prediction events with standardized demographic data.

    Reads feature values and maps them to demographic tags using
    lookup dictionaries. Produces enriched records for the
    fairops_enriched.demographics table.
    """

    # Feature keys to check for demographic data
    GENDER_KEYS = {"sex", "gender", "Sex", "Gender"}
    AGE_KEYS = {"age", "Age", "AGE"}
    RACE_KEYS = {"race", "Race", "ethnicity", "Ethnicity"}
    ZIP_KEYS = {"zip_code", "zipcode", "zip", "postal_code"}

    def process(self, element, *args, **kwargs):
        features = element.get("features")

        # Parse features if it's a JSON string
        if isinstance(features, str):
            try:
                features = json.loads(features)
            except json.JSONDecodeError:
                features = {}

        if not isinstance(features, dict):
            features = {}

        # Extract demographic values from features
        gender_dist = None
        race_dist = None
        age_bin = None
        zip_code = None

        for key, value in features.items():
            if key in self.GENDER_KEYS and gender_dist is None:
                gender_dist = _map_gender(value)
            elif key in self.AGE_KEYS and age_bin is None:
                age_bin = _classify_age(value)
            elif key in self.RACE_KEYS and race_dist is None:
                race_dist = _map_race(value)
            elif key in self.ZIP_KEYS and zip_code is None:
                zip_code = str(value).strip()

        # Build enriched record
        enriched_record = {
            "event_id": element.get("event_id"),
            "model_id": element.get("model_id"),
            "timestamp": element.get("timestamp"),
            "gender_distribution": json.dumps(gender_dist) if gender_dist else None,
            "race_distribution": json.dumps(race_dist) if race_dist else None,
            "age_bin": age_bin,
            "income_bracket": None,  # Populated in proxy mode (future sprint)
            "proxy_quality_score": 1.0 if (gender_dist or race_dist or age_bin) else None,
            "is_proxy": False,  # Direct label mapping, not proxy
            "zip_code": zip_code,
            "enriched_at": datetime.now(timezone.utc).isoformat(),
        }

        yield enriched_record
