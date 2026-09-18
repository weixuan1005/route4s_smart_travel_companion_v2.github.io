#!/usr/bin/env python3
"""
Check frontend/fares.json before you trust the prices on screen
===============================================================

    python3 tools/check_fares.py

The fare table is typed in by hand from a published tariff, so the likely faults are
transcription faults: a band out of order, a decimal point in the wrong place, a row skipped.
None of those raise an error at runtime - the app just shows a wrong price with a confident
face, which is worse than the estimate it replaced.

This reads the table, complains about anything structurally impossible, and prints the fare
curve so it can be held next to the published one and eyeballed.

Exit code 0 means the table is usable, 1 means it is not.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FARES = ROOT / "frontend" / "fares.json"


def main():
    if not FARES.exists():
        print(f"No {FARES.relative_to(ROOT)}. The app falls back to its own estimate and says so.")
        return 0
    try:
        t = json.loads(FARES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL  Not valid JSON: {e}")
        return 1

    bands = t.get("bands")
    if not isinstance(bands, list):
        print("FAIL  'bands' must be a list.")
        return 1
    if not bands:
        print("No bands yet, so fares are still the app's own estimate and are tagged as such.")
        print("Fill in 'bands' from the published table to show real fares.")
        return 0

    problems, warnings = [], []
    for i, b in enumerate(bands):
        if not isinstance(b, dict) or "max_km" not in b or "fare" not in b:
            problems.append(f"band {i}: needs both max_km and fare, got {b!r}")
            continue
        try:
            km, fare = float(b["max_km"]), float(b["fare"])
        except (TypeError, ValueError):
            problems.append(f"band {i}: max_km and fare must be numbers, got {b!r}")
            continue
        if km <= 0:
            problems.append(f"band {i}: max_km {km} is not a distance")
        if fare < 0:
            problems.append(f"band {i}: fare {fare} is negative")
        if fare == 0:
            warnings.append(f"band {i}: fare is 0.00 - a placeholder left in?")
        if fare > 10:
            warnings.append(f"band {i}: fare {fare} looks like a decimal point out of place")

    if problems:
        for p in problems:
            print("FAIL ", p)
        return 1

    rows = sorted(((float(b["max_km"]), float(b["fare"])) for b in bands), key=lambda r: r[0])
    for i in range(1, len(rows)):
        if rows[i][0] == rows[i-1][0]:
            problems.append(f"two bands both end at {rows[i][0]} km")
        if rows[i][1] < rows[i-1][1]:
            problems.append(f"fare falls from ${rows[i-1][1]:.2f} to ${rows[i][1]:.2f} "
                            f"between {rows[i-1][0]} km and {rows[i][0]} km - a longer trip cannot cost less")
        elif rows[i][1] - rows[i-1][1] > 1.00:
            warnings.append(f"fare jumps ${rows[i-1][1]:.2f} to ${rows[i][1]:.2f} between "
                            f"{rows[i-1][0]} km and {rows[i][0]} km - published bands step by cents")
    if problems:
        for p in problems:
            print("FAIL ", p)
        return 1

    for w in warnings:
        print("WARN ", w)

    src = t.get("source") or "(no source recorded)"
    eff = t.get("effective") or "(no effective date)"
    print(f"{len(rows)} bands · {src} · effective {eff} · {t.get('concession') or 'concession not stated'}")
    if not t.get("source") or not t.get("effective"):
        print("WARN  Record 'source', 'url' and 'effective' so the prices can be checked and refreshed.")
    print(f"      ${rows[0][1]:.2f} up to {rows[0][0]} km  →  ${rows[-1][1]:.2f} beyond {rows[-2][0] if len(rows) > 1 else rows[-1][0]} km")
    print()
    print("      Fare curve, to compare with the published table:")
    for km, fare in rows:
        print(f"        up to {km:>6.1f} km   ${fare:>5.2f}   {'#' * max(1, round(fare * 8))}")
    print()
    print("Usable. The app will show these and drop the 'Fare estimated' tag.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
