"""Build the dashboard dataset for the Ciénaga Grande de Santa Marta (Colombia).

Inputs: GEDI L2B v002 granules already downloaded (see scripts/download_l2b.py) and
an Earth Engine project for L4A and WorldCover. Outputs, in docs/data/:
* l2b.json: filtered L2B footprints with height, cover, PAI, FHD, WorldCover class,
  the 0.98 sensitivity flag and the PAVD profile up to 40 m;
* l4a.json: filtered L4A biomass footprints with class and the 0.98 sensitivity flag;
* summary.json: counts after each quality filter and medians by class.

USO: python scripts/build_dataset.py --granules D:/GEDI_L2B_CGSM/granulos --project my-ee-project
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from gedi_explorer.extract import WORLDCOVER, l2b_quality, read_l2b, read_l4a, worldcover_class  # noqa: E402

BBOX = (-74.86, 10.548, -74.205, 11.091)          # Ciénaga Grande de Santa Marta and surroundings (W, S, E, N)
CLASSES = [95, 90, 30, 10]                          # Mangroves, Herbaceous wetland, Grassland, Tree cover


def med(s):
    return None if len(s) == 0 else round(float(np.median(s)), 3)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--granules", required=True)
    p.add_argument("--project", required=True)
    a = p.parse_args()
    out = ROOT / "docs" / "data"; out.mkdir(parents=True, exist_ok=True)

    files = sorted(Path(a.granules).glob("GEDI02_B_*.h5"))
    shots, prof = read_l2b(files, BBOX)
    steps = {"L2B shots in the box": len(shots)}
    ok = l2b_quality(shots).values
    steps["after quality filters (sensitivity >= 0.95)"] = int(ok.sum())
    shots, prof = shots[ok].reset_index(drop=True), prof[ok]
    steps["... with sensitivity >= 0.98"] = int((shots.sensitivity >= 0.98).sum())
    shots["wc"] = worldcover_class(shots.lon.values, shots.lat.values, a.project)
    keep = shots.wc.isin(CLASSES).values
    shots, prof = shots[keep].reset_index(drop=True), prof[keep]
    steps["... on the four compared WorldCover classes"] = len(shots)

    pav = np.where(prof[:, :8] < 0, 0, prof[:, :8]).round(4)
    l2b = [{"x": round(r.lon, 6), "y": round(r.lat, 6), "c": int(r.wc), "h": round(r.rh100_m, 2), "cv": round(float(r.cover), 3),
            "pai": round(float(r.pai), 3), "fhd": round(float(r.fhd_normal), 3), "s98": int(r.sensitivity >= 0.98),
            "d": r.date, "p": pav[i].tolist()} for i, r in enumerate(shots.itertuples())]
    (out / "l2b.json").write_text(json.dumps(l2b, separators=(",", ":")), encoding="utf-8")

    l4 = read_l4a(BBOX, a.project)
    l4 = l4[l4.wc.isin(CLASSES)].reset_index(drop=True)
    l4a = [{"x": round(r.lon, 6), "y": round(r.lat, 6), "c": int(r.wc), "b": round(float(r.agbd), 1),
            "s98": int(r.sensitivity >= 0.98), "d": r.date} for r in l4.itertuples()]
    (out / "l4a.json").write_text(json.dumps(l4a, separators=(",", ":")), encoding="utf-8")

    by_class = {}
    for c in CLASSES:
        s, b = shots[shots.wc == c], l4[l4.wc == c]
        by_class[WORLDCOVER[c]] = {
            "l2b_n": len(s), "rh100_m": med(s.rh100_m), "cover": med(s.cover), "pai": med(s.pai), "fhd": med(s.fhd_normal),
            "l4a_n": len(b), "agbd_median": med(b.agbd), "agbd_median_s98": med(b[b.sensitivity >= 0.98].agbd),
            "agbd_mean": None if len(b) == 0 else round(float(b.agbd.mean()), 1),
            "agbd_mean_s98": None if (b.sensitivity >= 0.98).sum() == 0 else round(float(b[b.sensitivity >= 0.98].agbd.mean()), 1)}
    summary = {"bbox": BBOX, "l2b_steps": steps, "l2b_dates": [shots.date.min(), shots.date.max()],
               "l4a_n": len(l4), "l4a_n_s98": int((l4.sensitivity >= 0.98).sum()), "l4a_dates": [l4.date.min(), l4.date.max()],
               "by_class": by_class, "classes": {str(c): WORLDCOVER[c] for c in CLASSES}}
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("sizes (KB):", {f.name: round(f.stat().st_size / 1024) for f in out.glob("*.json")})


if __name__ == "__main__":
    main()
