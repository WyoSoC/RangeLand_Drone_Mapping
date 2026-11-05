#!/usr/bin/env python3
"""Inventory DJI drone images: GPS, altitude, gimbal angles, capture time.

Pure standard library (no Pillow/exiftool needed). Reads the DJI XMP block
and the EXIF capture timestamp from the JPEG header.

Usage:
    python3 scripts/inventory_images.py <image_dir> [-o inventory.csv] [--geojson out.geojson]
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

HEADER_BYTES = 256 * 1024  # EXIF + XMP live in the first few tens of KB

XMP_FIELDS = {
    "lat": "GpsLatitude",
    "lon": "GpsLongitude",
    "abs_alt": "AbsoluteAltitude",
    "rel_alt": "RelativeAltitude",
    "gimbal_pitch": "GimbalPitchDegree",
    "gimbal_yaw": "GimbalYawDegree",
    "gimbal_roll": "GimbalRollDegree",
    "flight_yaw": "FlightYawDegree",
}
DATE_RE = re.compile(rb"(\d{4}:\d\d:\d\d \d\d:\d\d:\d\d)")


def read_meta(path: Path) -> dict:
    with open(path, "rb") as f:
        head = f.read(HEADER_BYTES)
    row = {"file": path.name}
    for key, tag in XMP_FIELDS.items():
        m = re.search(rb'drone-dji:' + tag.encode() + rb'="([^"]+)"', head)
        row[key] = float(m.group(1)) if m else None
    m = DATE_RE.search(head)
    row["datetime"] = m.group(1).decode().replace(":", "-", 2) if m else None
    m = re.search(rb'tiff:Model="([^"]+)"', head) or re.search(rb"(FC\d{4})", head)
    row["model"] = m.group(1).decode() if m else None
    return row


def haversine_m(a, b):
    R = 6371000.0
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * R * math.asin(math.sqrt(h))


def summarize(rows):
    ok = [r for r in rows if r["lat"] is not None]
    if not ok:
        return "No geotagged images found."
    lats = [r["lat"] for r in ok]
    lons = [r["lon"] for r in ok]
    rel = [r["rel_alt"] for r in ok if r["rel_alt"] is not None]
    pitch = [r["gimbal_pitch"] for r in ok if r["gimbal_pitch"] is not None]
    times = sorted(r["datetime"] for r in ok if r["datetime"])
    # nearest-neighbour spacing between consecutive shots (proxy for forward overlap)
    seq = sorted(ok, key=lambda r: r["file"])
    steps = [haversine_m((a["lat"], a["lon"]), (b["lat"], b["lon"])) for a, b in zip(seq, seq[1:])]
    width_m = haversine_m((min(lats), min(lons)), (min(lats), max(lons)))
    height_m = haversine_m((min(lats), min(lons)), (max(lats), min(lons)))
    lines = [
        f"Images:              {len(rows)} ({len(ok)} geotagged)",
        f"Camera model(s):     {sorted(set(r['model'] for r in rows if r['model']))}",
        f"Time span:           {times[0]} -> {times[-1]}" if times else "Time span: n/a",
        f"Bounding box:        lat {min(lats):.6f}..{max(lats):.6f}, lon {min(lons):.6f}..{max(lons):.6f}",
        f"Extent (approx):     {width_m:.0f} m E-W x {height_m:.0f} m N-S",
        f"Centroid:            {statistics.mean(lats):.6f}, {statistics.mean(lons):.6f}",
        f"Relative altitude:   min {min(rel):.1f} / median {statistics.median(rel):.1f} / max {max(rel):.1f} m (above takeoff)",
        f"Gimbal pitch:        min {min(pitch):.1f} / median {statistics.median(pitch):.1f} / max {max(pitch):.1f} deg",
        f"Non-nadir (>-80deg): {sum(1 for p in pitch if p > -80)} images",
        f"Shot spacing:        median {statistics.median(steps):.1f} m between consecutive images",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image_dir", type=Path)
    ap.add_argument("-o", "--csv", type=Path, help="write per-image CSV")
    ap.add_argument("--geojson", type=Path, help="write camera positions as GeoJSON points")
    args = ap.parse_args()

    files = sorted(p for p in args.image_dir.iterdir() if p.suffix.lower() in (".jpg", ".jpeg"))
    if not files:
        sys.exit(f"No JPG files in {args.image_dir}")
    rows = [read_meta(p) for p in files]

    if args.csv:
        args.csv.parent.mkdir(parents=True, exist_ok=True)
        with open(args.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    if args.geojson:
        args.geojson.parent.mkdir(parents=True, exist_ok=True)
        feats = [
            {"type": "Feature",
             "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"], r["abs_alt"]]},
             "properties": {k: v for k, v in r.items() if k not in ("lat", "lon")}}
            for r in rows if r["lat"] is not None
        ]
        args.geojson.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))

    print(f"== {args.image_dir}")
    print(summarize(rows))


if __name__ == "__main__":
    main()
