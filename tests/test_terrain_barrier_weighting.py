"""
Unit tests for Province Scoring and Automatic River/Barrier Bisection
in `backend/tools/terrain_barrier_analyzer.py` and `backend/tools/compiler.py`.
"""

import sys
from pathlib import Path
from shapely.geometry import box

sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.tools.terrain_barrier_analyzer import (
    get_terrain_db,
    bisect_unit_by_river,
    score_province,
    prepare_scored_and_bisected_units,
)
from backend.models.schemas import TerritoryChange
from backend.tools.compiler import process_territory_definitions


def test_province_scoring_lowland_vs_alpine():
    """Verify that lowland river plains receive higher expansion scores than alpine mountain massifs."""
    # Alföld / Great Hungarian Plain box vs High Alps (Tyrol) box
    alfold_box = box(19.0, 46.2, 21.2, 47.6)
    tyrol_alps_box = box(10.5, 46.8, 12.5, 47.5)
    conq_front = box(18.5, 44.5, 21.5, 46.2)

    sc_plain = score_province("Alföld (Great Hungarian Plain)", alfold_box, conq_front)
    sc_alps = score_province("Tyrol", tyrol_alps_box, conq_front)

    assert sc_plain["score_real"] > sc_alps["score_real"]
    assert sc_plain["score_opt"] > sc_alps["score_opt"]
    assert sc_alps["mountain_pct"] > 50.0


def test_river_bisection_and_independent_partition_scoring():
    """Verify that a historical unit cut by the Danube is bisected along the river and each partition is scored."""
    db = get_terrain_db()
    danube = db.rivers_by_name.get("Danube")
    assert danube is not None

    lower_austria_box = box(14.6, 47.8, 16.8, 48.9)
    southern_conqueror = box(16.0, 46.0, 19.0, 47.7)

    bisect_res = bisect_unit_by_river(
        unit_name="Lower Austria (Vienna)",
        unit_geom=lower_austria_box,
        river_name="Danube",
        river_geom=danube,
        conqueror_geom=southern_conqueror,
    )
    assert bisect_res is not None
    assert bisect_res["near_name"] == "Lower Austria (Vienna) (South of Danube)"
    assert bisect_res["far_name"] == "Lower Austria (Vienna) (North of Danube)"
    assert bisect_res["near_geom"].area > 0.3
    assert bisect_res["far_geom"].area > 0.3
    assert abs((bisect_res["near_geom"].area + bisect_res["far_geom"].area) - lower_austria_box.area) < 0.05

    sc_near = score_province(
        bisect_res["near_name"],
        bisect_res["near_geom"],
        southern_conqueror,
        is_far_bank=False,
        bisecting_river="Danube",
    )
    sc_far = score_province(
        bisect_res["far_name"],
        bisect_res["far_geom"],
        southern_conqueror,
        is_far_bank=True,
        bisecting_river="Danube",
    )

    # Near bank should score higher in Realistic mode than the far bank across the Danube
    assert sc_near["score_real"] > sc_far["score_real"]
    # Far bank should have a higher Optimistic score than Realistic score (allowing bridgehead expansion in Optimistic)
    assert sc_far["score_opt"] > sc_far["score_real"]


def test_prepare_and_compile_bisected_province():
    """Verify that `prepare_scored_and_bisected_units` registers bisected river units and `compiler.py` resolves them."""
    avail_units = {"Lower Austria (Vienna)"}
    unit_geom_map = {"Lower Austria (Vienna)": box(14.6, 47.8, 16.8, 48.9)}
    unit_polity_map = {"Lower Austria (Vienna)": "Archduchy of Austria"}
    unit_meta_lookup = {"Lower Austria (Vienna)": {"capital_modern": "Vienna", "tier": "Archduchy"}}
    conq_base = box(16.0, 46.0, 19.0, 47.8)
    context = {
        "scenario": "Ottoman advance to the Danube River at Vienna in 1529",
        "baseline_polities": ["Ottoman Empire", "Archduchy of Austria"],
        "parties": ["Ottoman Empire", "Archduchy of Austria"],
    }

    briefing = prepare_scored_and_bisected_units(
        all_available_units=avail_units,
        unit_geom_map=unit_geom_map,
        unit_polity_map=unit_polity_map,
        unit_meta_lookup=unit_meta_lookup,
        winner_base_sh=conq_base,
        scenario_val=context["scenario"],
        context_val=context,
    )

    assert "Lower Austria (Vienna) (South of Danube)" in avail_units
    assert "Lower Austria (Vienna) (North of Danube)" in avail_units
    assert "ProvinceScore[Real=" in briefing
    assert "dynamic_bisected_units" in context
    assert "Lower Austria (Vienna) (South of Danube)" in context["dynamic_bisected_units"]

    # Verify compiler resolves the bisected sub-province geometry cleanly
    t_change = TerritoryChange(
        name="Ottoman Empire",
        type="empire",
        description="Conquest up to the Danube",
        color="#10b981",
        countries_absorbed=[],
        partial_countries=[],
        historical_provinces=["Lower Austria (Vienna) (South of Danube)"],
    )
    feats = process_territory_definitions([t_change], 1529, context)
    assert len(feats) >= 1

