import pytest

from app.core.uk import (
    normalise_postcode,
    normalise_postcode_prefix,
    normalise_uk_phone,
    postcode_is_covered,
)
from app.models import PriceType
from app.schemas.catalogue import format_price


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("07911 123456", "+447911123456"),
        ("+44 7911 123456", "+447911123456"),
        ("0044 7911 123456", "+447911123456"),
        ("020 7946 0958", "+442079460958"),
    ],
)
def test_uk_phone_normalised_to_e164(raw: str, expected: str) -> None:
    assert normalise_uk_phone(raw) == expected


@pytest.mark.parametrize("raw", ["12345", "+1 202 555 0143", "not a number", ""])
def test_invalid_or_non_uk_phone_rejected(raw: str) -> None:
    with pytest.raises(ValueError, match="UK phone"):
        normalise_uk_phone(raw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("sw1a1aa", "SW1A 1AA"),
        ("M1 1AE", "M1 1AE"),
        (" b33  8th ", "B33 8TH"),
        ("CR2 6XH", "CR2 6XH"),
    ],
)
def test_postcode_normalised(raw: str, expected: str) -> None:
    assert normalise_postcode(raw) == expected


@pytest.mark.parametrize("raw", ["ABC 123", "12345", "SW1A", ""])
def test_invalid_postcode_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        normalise_postcode(raw)


@pytest.mark.parametrize(("raw", "expected"), [(" m1 ", "M1"), ("sw1a", "SW1A"), ("M", "M")])
def test_postcode_prefix_normalised(raw: str, expected: str) -> None:
    assert normalise_postcode_prefix(raw) == expected


@pytest.mark.parametrize("raw", ["123", "M1 1AE", "TOOLONG"])
def test_invalid_postcode_prefix_rejected(raw: str) -> None:
    with pytest.raises(ValueError):
        normalise_postcode_prefix(raw)


def test_coverage_by_district_and_area() -> None:
    assert postcode_is_covered("M1 1AE", ["M1"])
    assert not postcode_is_covered("M2 1AA", ["M1"])
    assert postcode_is_covered("M2 1AA", ["M"])  # whole area
    # "M" must not match the "ML" (Motherwell) area.
    assert not postcode_is_covered("ML1 1AA", ["M"])
    assert not postcode_is_covered("SW1A 1AA", [])


@pytest.mark.parametrize(
    ("price_type", "minor", "expected"),
    [
        (PriceType.FIXED, 12500, "£125"),
        (PriceType.FIXED, 9999, "£99.99"),
        (PriceType.FROM, 185000, "from £1,850"),
        (PriceType.QUOTE, None, "Priced after a survey"),
    ],
)
def test_price_display(price_type: PriceType, minor: int | None, expected: str) -> None:
    assert format_price(price_type, minor) == expected
