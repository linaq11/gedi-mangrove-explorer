"""Extract GEDI L2B (canopy structure) and L4A (biomass) footprints for an area of interest.

L2B is read from the HDF5 granules (exact footprint coordinates, vertical PAVD
profiles). L4A is read from Google Earth Engine (LARSE/GEDI/GEDI04_A_002_MONTHLY),
where each footprint sits at the centre of its 25 m cell because the
lat_lowestmode / lon_lowestmode bands are empty in that collection. Each footprint
gets its ESA WorldCover 2021 class, so the comparison between mangrove and the
other covers uses a public map.
"""
from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pandas as pd

FULL_POWER_BEAMS = {"BEAM0101", "BEAM0110", "BEAM1000", "BEAM1011"}
FILL = -9999
L2B_VARS = {
    "shot_number": "shot_number", "lat": "geolocation/lat_lowestmode", "lon": "geolocation/lon_lowestmode",
    "elev_lowestmode": "geolocation/elev_lowestmode", "dem": "geolocation/digital_elevation_model",
    "degrade_flag": "geolocation/degrade_flag", "solar_elevation": "geolocation/solar_elevation",
    "delta_time": "geolocation/delta_time", "l2b_quality_flag": "l2b_quality_flag", "sensitivity": "sensitivity",
    "cover": "cover", "pai": "pai", "fhd_normal": "fhd_normal", "rh100_cm": "rh100",
}
WORLDCOVER = {10: "Tree cover", 20: "Shrubland", 30: "Grassland", 40: "Cropland", 50: "Built-up", 60: "Bare",
              80: "Water", 90: "Herbaceous wetland", 95: "Mangroves", 100: "Moss and lichen"}


def read_l2b(files: list[Path], bbox: tuple[float, float, float, float]) -> tuple[pd.DataFrame, np.ndarray]:
    """All L2B shots inside ``bbox`` (W, S, E, N) with their PAVD profiles (5 m bins)."""
    frames, profiles = [], []
    for f in files:
        with h5py.File(f, "r") as h5:
            for beam in sorted(k for k in h5 if k.startswith("BEAM")):
                g = h5[beam]
                lat, lon = g["geolocation/lat_lowestmode"][:], g["geolocation/lon_lowestmode"][:]
                m = (lon >= bbox[0]) & (lon <= bbox[2]) & (lat >= bbox[1]) & (lat <= bbox[3])
                idx = np.flatnonzero(m)
                if idx.size == 0:
                    continue
                i0, i1 = idx.min(), idx.max() + 1
                sel = m[i0:i1]
                df = pd.DataFrame({c: g[p][i0:i1][sel] for c, p in L2B_VARS.items()})
                df["beam"], df["granule"] = beam, Path(f).name
                frames.append(df)
                profiles.append(g["pavd_z"][i0:i1][sel].astype("float32"))
    shots = pd.concat(frames, ignore_index=True)
    shots["shot_number"] = shots["shot_number"].astype("uint64").astype(str)
    shots["power"] = np.where(shots.beam.isin(FULL_POWER_BEAMS), "full", "coverage")
    shots["rh100_m"] = shots.rh100_cm / 100.0
    shots["date"] = (pd.Timestamp("2018-01-01") + pd.to_timedelta(shots.delta_time, unit="s")).dt.strftime("%Y-%m-%d")
    return shots, np.vstack(profiles)


def l2b_quality(shots: pd.DataFrame) -> pd.Series:
    """Quality filter from the GEDI training material: L2B quality flag, no degraded
    pointing, sensitivity of 0.95 or more, valid values and a lowest mode within
    50 m of the reference DEM."""
    ok = (shots.l2b_quality_flag == 1) & (shots.degrade_flag == 0) & (shots.sensitivity >= 0.95)
    ok &= (shots.cover != FILL) & (shots.pai != FILL) & (shots.fhd_normal != FILL) & (shots.rh100_cm != FILL)
    ok &= (shots.elev_lowestmode - shots.dem).abs() < 50
    return ok


def worldcover_class(lon, lat, project: str) -> np.ndarray:
    """ESA WorldCover 2021 class at each point, sampled in Earth Engine."""
    import ee
    ee.Initialize(project=project)
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().rename("wc")
    out = np.zeros(len(lon), dtype=int)
    for i in range(0, len(lon), 4000):
        fc = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(x), float(y)]), {"k": i + j})
                                   for j, (x, y) in enumerate(zip(lon[i:i + 4000], lat[i:i + 4000]))])
        for f in wc.reduceRegions(fc, ee.Reducer.first(), 10).getInfo()["features"]:
            out[f["properties"]["k"]] = f["properties"].get("first") or 0
    return out


def read_l4a(bbox: tuple[float, float, float, float], project: str, start: str = "2019-04-01", end: str = "2026-01-01") -> pd.DataFrame:
    """L4A biomass footprints with quality flag 1, no degradation and sensitivity of
    0.95 or more, from Earth Engine; WorldCover class added in the same pass."""
    import ee
    ee.Initialize(project=project)
    aoi = ee.Geometry.Rectangle(list(bbox))
    wc = ee.ImageCollection("ESA/WorldCover/v200").first().rename("wc")
    col = ee.ImageCollection("LARSE/GEDI/GEDI04_A_002_MONTHLY").filterBounds(aoi).filterDate(start, end)

    def good(im):
        m = im.select("l4_quality_flag").eq(1).And(im.select("degrade_flag").eq(0)).And(im.select("sensitivity").gte(0.95))
        return (im.select(["agbd", "agbd_se", "sensitivity", "solar_elevation", "beam", "delta_time"]).addBands(wc)
                .updateMask(m).sample(region=aoi, scale=25, dropNulls=True, geometries=True))
    fc = col.map(good).flatten()
    n = fc.size().getInfo()
    rows = []
    for i in range(0, n, 5000):
        rows += [dict(lon=f["geometry"]["coordinates"][0], lat=f["geometry"]["coordinates"][1], **f["properties"])
                 for f in fc.toList(5000, i).getInfo()]
    df = pd.DataFrame(rows).drop_duplicates(["lon", "lat", "delta_time"]).reset_index(drop=True)
    df["date"] = (pd.Timestamp("2018-01-01") + pd.to_timedelta(df.delta_time, unit="s")).dt.strftime("%Y-%m-%d")
    df["power"] = np.where(df.beam.isin([5, 6, 8, 11]), "full", "coverage")
    return df
