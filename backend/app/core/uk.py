"""UK-specific validation: phone numbers (stored as E.164) and postcodes."""

import re

import phonenumbers

# Full postcode, e.g. "SW1A 1AA", "M1 1AE", "B33 8TH". Validates shape only; real-world
# existence is checked against postcodes.io in Phase 3.
_FULL_POSTCODE = re.compile(r"^([A-Z]{1,2}\d[A-Z\d]?) ?(\d[A-Z]{2})$")
# Coverage prefix: a postcode area ("M", "SW") or district ("M1", "SW1A", "B33").
_POSTCODE_PREFIX = re.compile(r"^[A-Z]{1,2}(\d[A-Z\d]?)?$")


def normalise_uk_phone(value: str) -> str:
    """Return E.164 (e.g. +447700900123). Accepts national (07700 900123) or +44 forms."""
    try:
        number = phonenumbers.parse(value, "GB")
    except phonenumbers.NumberParseException as exc:
        raise ValueError("Enter a valid UK phone number") from exc
    if not phonenumbers.is_valid_number(number) or number.country_code != 44:
        raise ValueError("Enter a valid UK phone number")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def normalise_postcode(value: str) -> str:
    """Return the canonical form 'OUTWARD INWARD', e.g. 'sw1a1aa' -> 'SW1A 1AA'."""
    compact = re.sub(r"\s+", "", value).upper()
    match = _FULL_POSTCODE.match(compact)
    if not match:
        raise ValueError("Enter a valid UK postcode")
    return f"{match.group(1)} {match.group(2)}"


def outward_code(postcode: str) -> str:
    return normalise_postcode(postcode).split(" ")[0]


def normalise_postcode_prefix(value: str) -> str:
    """Coverage prefix: postcode area or district, e.g. ' m1 ' -> 'M1'."""
    compact = re.sub(r"\s+", "", value).upper()
    if not _POSTCODE_PREFIX.match(compact):
        raise ValueError("Enter a postcode area (e.g. M) or district (e.g. M1, SW1A)")
    return compact


def postcode_area(prefix_or_outward: str) -> str:
    """'SW1A' -> 'SW', 'M1' -> 'M'."""
    match = re.match(r"^[A-Z]{1,2}", prefix_or_outward)
    if not match:
        raise ValueError("Invalid postcode prefix")
    return match.group(0)


def postcode_is_covered(postcode: str, prefixes: list[str]) -> bool:
    """True if the postcode's district or area is in the coverage list."""
    district = outward_code(postcode)
    area = postcode_area(district)
    return district in prefixes or area in prefixes
