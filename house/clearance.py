"""Rule-only clearance estimator for a home battery stack (issue #34).

No images. This is a first-pass geometry heuristic based on install rules
member reports gave us:

- A battery stack needs about 9 ft of clear exterior wall per battery.
- The stack needs 3 ft of setback from the gas meter, the A/C condenser,
  and the fence. It goes next to the electric meter and the main panel.

Method: model the lot and the house footprint as rectangles. The house
footprint uses a 1.5 aspect ratio (long side = 1.5 x short side). The lot
uses a 1.8 aspect ratio. Side setback is estimated from the leftover lot
width after the house footprint sits inside it. A detached garage eats one
full wall (rear or side) from the usable perimeter, since installers avoid
putting a battery stack against a garage wall shared with a driveway path.

This is a rule-only stand-in for a real site plan. It does not look at
photos, GIS parcel data, or actual setback ordinances. Treat the output as
"should we send a tech" triage, not permitting fact.
"""

import argparse
import math

WALL_FT_PER_BATTERY = 9.0
GAS_METER_SETBACK_FT = 3.0
CONDENSER_SETBACK_FT = 3.0
FENCE_SETBACK_FT = 3.0
FOOTPRINT_ASPECT = 1.5
LOT_ASPECT = 1.8

SMALL_LOT_SQFT = 4500
LARGE_LOT_SQFT = 7000
HIGH_COVERAGE_RATIO = 0.4


def _rect_dims(area, aspect):
    """Return (short_side, long_side) for a rectangle of the given area and
    aspect ratio (long / short)."""
    short = math.sqrt(area / aspect)
    long_ = short * aspect
    return short, long_


def estimate_clearance(
    lot_sqft,
    footprint_sqft,
    storeys,
    garage_detached=False,
    garage_sqft=0,
    year_built=None,
    has_gas=None,
):
    """Estimate battery-stack wall clearance for one house.

    Args:
        lot_sqft: total lot area, sq ft.
        footprint_sqft: main house footprint (ground floor area). For a
            2-storey house this is still just the ground floor area, since
            the second floor sits on top and does not add footprint.
        storeys: 1 or 2. Does not change wall length in this model.
        garage_detached: True if there is a detached garage.
        garage_sqft: detached garage footprint, sq ft (ignored if attached
            or garage_detached is False).
        year_built: house year built. Not used in this rule-only pass
            (reserved for a later revision that adjusts for older panels/
            setback code eras). Accepted so callers can pass what they have.
        has_gas: True/False/None. None means unknown, which is allowed and
            is treated as "assume gas meter present" for the conservative
            side of clearance planning.

    Returns:
        dict with clearance_ok, wall_estimate_ft, side_setback_ft_estimate,
        reasons, photo_to_ask, confidence.
    """
    reasons = []

    house_short, house_long = _rect_dims(footprint_sqft, FOOTPRINT_ASPECT)
    lot_short, lot_long = _rect_dims(lot_sqft, LOT_ASPECT)

    # Side setback: leftover lot width on each side of the house, split
    # evenly. Floor at 0 (house wider than lot means zero-lot-line-like).
    side_setback = max((lot_short - house_short) / 2.0, 0.0)
    side_setback = round(side_setback, 1)

    # Usable exterior wall for the stack: the shorter side of the house
    # footprint, since installers put the stack on the side yard, not the
    # front or rear where doors/windows dominate.
    usable_wall = house_short

    if garage_detached and garage_sqft > 0:
        garage_short, _ = _rect_dims(garage_sqft, FOOTPRINT_ASPECT)
        usable_wall = max(usable_wall - garage_short, 0.0)
        reasons.append(
            f"Detached garage ({garage_sqft:.0f} sq ft) eats about "
            f"{garage_short:.1f} ft off the usable side/rear wall."
        )

    wall_estimate = round(usable_wall, 1)

    if has_gas is None:
        reasons.append(
            "Gas service unknown; assuming a gas meter is present for the "
            f"conservative {GAS_METER_SETBACK_FT:.0f} ft setback."
        )
    elif has_gas:
        reasons.append(f"Gas meter present; needs {GAS_METER_SETBACK_FT:.0f} ft setback.")
    else:
        reasons.append("No gas service reported; gas meter setback does not apply.")

    reasons.append(
        f"Side setback estimate: {side_setback:.1f} ft (lot short side "
        f"{lot_short:.1f} ft minus house short side {house_short:.1f} ft, split "
        "both sides)."
    )
    reasons.append(
        f"Usable exterior wall estimate: {wall_estimate:.1f} ft "
        f"(house short side{' minus garage' if garage_detached and garage_sqft else ''})."
    )

    # storeys does not change wall length in this model; note it so the
    # reasoning is auditable.
    reasons.append(f"{storeys}-storey house: footprint used as-is, wall length unchanged.")

    coverage_ratio = footprint_sqft / lot_sqft if lot_sqft else 1.0

    # Decide clearance_ok.
    if coverage_ratio > HIGH_COVERAGE_RATIO:
        clearance_ok = "unlikely"
        reasons.append(
            f"Footprint covers {coverage_ratio:.0%} of the lot, over the "
            f"{HIGH_COVERAGE_RATIO:.0%} threshold; this pattern matches a "
            "zero-lot-line or tight-yard build where side clearance is "
            "usually built out to (or past) the property line."
        )
        confidence = "medium"
    elif lot_sqft > LARGE_LOT_SQFT:
        clearance_ok = "likely"
        reasons.append(f"Lot over {LARGE_LOT_SQFT} sq ft: likely enough room.")
        confidence = "medium"
    elif lot_sqft < SMALL_LOT_SQFT and garage_detached:
        clearance_ok = "unclear"
        reasons.append(
            f"Lot under {SMALL_LOT_SQFT} sq ft with a detached garage: unclear, "
            "needs a site check."
        )
        confidence = "low"
    elif side_setback < FENCE_SETBACK_FT:
        clearance_ok = "unlikely"
        reasons.append(
            f"Side setback ({side_setback:.1f} ft) is under the {FENCE_SETBACK_FT:.0f} ft "
            "fence setback needed; likely too tight."
        )
        confidence = "medium"
    elif wall_estimate < WALL_FT_PER_BATTERY:
        clearance_ok = "unlikely"
        reasons.append(
            f"Usable wall estimate ({wall_estimate:.1f} ft) is under the "
            f"{WALL_FT_PER_BATTERY:.0f} ft needed for one battery."
        )
        confidence = "medium"
    else:
        clearance_ok = "unclear"
        confidence = "low"

    photo_to_ask = (
        "Please take a photo from about 10 ft back, facing the side exterior "
        "wall nearest the electric meter and main panel, showing the ground "
        "clear of AC units, gas meters, and fencing."
    )

    return {
        "clearance_ok": clearance_ok,
        "wall_estimate_ft": wall_estimate,
        "side_setback_ft_estimate": side_setback,
        "reasons": reasons,
        "photo_to_ask": photo_to_ask,
        "confidence": confidence,
    }


DEMO_CASES = [
    {
        "label": "(a) small lot, 2-storey, detached garage -> expect unclear",
        "kwargs": dict(
            lot_sqft=3877,
            footprint_sqft=868,
            storeys=2,
            garage_detached=True,
            garage_sqft=420,
            year_built=1962,
            has_gas=None,
        ),
    },
    {
        "label": "(b) large lot, 1-storey, attached garage -> expect likely",
        "kwargs": dict(
            lot_sqft=8000,
            footprint_sqft=1800,
            storeys=1,
            garage_detached=False,
            garage_sqft=0,
            year_built=1995,
            has_gas=True,
        ),
    },
    {
        "label": "(c) small lot, 1-storey, zero-lot-line -> expect unlikely",
        "kwargs": dict(
            lot_sqft=3000,
            footprint_sqft=1400,
            storeys=1,
            garage_detached=False,
            garage_sqft=0,
            year_built=2005,
            has_gas=True,
        ),
    },
]


def run_demo():
    for case in DEMO_CASES:
        print(f"\n{case['label']}")
        result = estimate_clearance(**case["kwargs"])
        print(f"  clearance_ok: {result['clearance_ok']}")
        print(f"  wall_estimate_ft: {result['wall_estimate_ft']}")
        print(f"  side_setback_ft_estimate: {result['side_setback_ft_estimate']}")
        print(f"  confidence: {result['confidence']}")
        print("  reasons:")
        for reason in result["reasons"]:
            print(f"    - {reason}")
        print(f"  photo_to_ask: {result['photo_to_ask']}")


def main():
    parser = argparse.ArgumentParser(description="Battery stack clearance estimator (rule-only).")
    parser.add_argument("--demo", action="store_true", help="Run three demo cases.")
    parser.add_argument("--lot-sqft", type=float)
    parser.add_argument("--footprint-sqft", type=float)
    parser.add_argument("--storeys", type=int, choices=[1, 2])
    parser.add_argument("--garage-detached", action="store_true")
    parser.add_argument("--garage-sqft", type=float, default=0)
    parser.add_argument("--year-built", type=int, default=None)
    parser.add_argument(
        "--has-gas",
        choices=["true", "false", "unknown"],
        default="unknown",
    )
    args = parser.parse_args()

    if args.demo:
        run_demo()
        return

    if args.lot_sqft is None or args.footprint_sqft is None or args.storeys is None:
        parser.error("--lot-sqft, --footprint-sqft, and --storeys are required unless --demo")

    has_gas = {"true": True, "false": False, "unknown": None}[args.has_gas]

    result = estimate_clearance(
        lot_sqft=args.lot_sqft,
        footprint_sqft=args.footprint_sqft,
        storeys=args.storeys,
        garage_detached=args.garage_detached,
        garage_sqft=args.garage_sqft,
        year_built=args.year_built,
        has_gas=has_gas,
    )
    import json

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
