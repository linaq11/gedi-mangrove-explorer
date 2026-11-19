import json
from pathlib import Path

import pandas as pd

from gedi_explorer.extract import FILL, l2b_quality

DATA = Path(__file__).resolve().parents[1] / "docs" / "data"


def shot(**kw):
    base = dict(l2b_quality_flag=1, degrade_flag=0, sensitivity=0.97, cover=0.5, pai=1.0, fhd_normal=2.0,
                rh100_cm=1500, elev_lowestmode=3.0, dem=5.0)
    base.update(kw)
    return base


def test_quality_filter_keeps_good_and_drops_each_failure():
    df = pd.DataFrame([shot(), shot(l2b_quality_flag=0), shot(degrade_flag=1), shot(sensitivity=0.9),
                       shot(cover=FILL), shot(rh100_cm=FILL), shot(elev_lowestmode=80.0)])
    assert l2b_quality(df).tolist() == [True, False, False, False, False, False, False]


def test_dashboard_data_matches_its_summary():
    l2b = json.loads((DATA / "l2b.json").read_text())
    l4a = json.loads((DATA / "l4a.json").read_text())
    s = json.loads((DATA / "summary.json").read_text())
    assert len(l2b) == s["l2b_steps"]["... on the four compared WorldCover classes"]
    assert len(l4a) == s["l4a_n"] and sum(r["s98"] for r in l4a) == s["l4a_n_s98"]
    mang = sorted(r["h"] for r in l2b if r["c"] == 95)
    med = (mang[len(mang) // 2] + mang[(len(mang) - 1) // 2]) / 2
    assert abs(med - s["by_class"]["Mangroves"]["rh100_m"]) < 0.01
    assert all(len(r["p"]) == 8 for r in l2b) and {r["c"] for r in l2b} <= {95, 90, 30, 10}
