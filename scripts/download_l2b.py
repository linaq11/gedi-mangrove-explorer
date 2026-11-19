"""Download GEDI L2B v002 granules that intersect a box, with your own NASA Earthdata login.

USO: python scripts/download_l2b.py --out data/l2b --start 2024-04-01 --end 2025-12-31
Size check first: the 33 granules for the Ciénaga Grande box in 2024-2025 weigh about 10.8 GB.
"""
import argparse

import earthaccess

BBOX = (-74.86, 10.548, -74.205, 11.091)

p = argparse.ArgumentParser()
p.add_argument("--out", required=True)
p.add_argument("--start", default="2024-04-01")
p.add_argument("--end", default="2025-12-31")
p.add_argument("--dry-run", action="store_true", help="only list the granules and their total size")
a = p.parse_args()
earthaccess.login()
res = earthaccess.search_data(short_name="GEDI02_B", version="002", bounding_box=BBOX, temporal=(a.start, a.end))
print(f"{len(res)} granules, {sum(float(g.size) for g in res) / 1024:.1f} GB")
if not a.dry_run:
    earthaccess.download(res, local_path=a.out)
