"""
test_shirt_library.py -- pytest suite for shirt_library.py and
validate_shirt_library.py (Phase 2, operation library).

Run with: pytest test_shirt_library.py -v
"""
from __future__ import annotations

import json

import pandas as pd
import pytest

import handling_time as ht
import machine_time as mt
import allowance as al
import smv_assembly as sa
import shirt_library as sl
import validate_shirt_library as vsl


@pytest.fixture(scope="module")
def seam_geom():
    return json.load(open("seam_geometry.json"))


@pytest.fixture(scope="module")
def tax():
    return ht.load_taxonomy("element_taxonomy.json")


@pytest.fixture(scope="module")
def mcat():
    return mt.load_machine_catalog("machine_classes.csv")


@pytest.fixture(scope="module")
def pol():
    return al.load_allowance_policy("allowance_policy.json")


# --------------------------------------------------------------------------
# build_seam_operation / build_cycle_operation
# --------------------------------------------------------------------------

class TestOperationBuilders:
    def test_every_seam_operation_builds_without_error(self, seam_geom, tax, mcat, pol):
        for op_spec in seam_geom["seam_operations"]:
            op = sl.build_seam_operation(op_spec, "M")
            result = sa.assemble_operation(tax, mcat, pol, op)
            assert result["ST_op_s"] > 0
            assert not result["no_double_count_warnings"]

    def test_every_cycle_operation_builds_without_error(self, seam_geom, tax, mcat, pol):
        for op_spec in seam_geom["cycle_operations"]:
            op = sl.build_cycle_operation(op_spec, "M")
            result = sa.assemble_operation(tax, mcat, pol, op)
            assert result["ST_op_s"] > 0

    def test_join_keyword_selects_ham(self, seam_geom):
        join_op = next(o for o in seam_geom["seam_operations"]
                       if o["operation"] == "Attach cuff to sleeve")
        op = sl.build_seam_operation(join_op, "M")
        elements = [s["element"] for s in op.steps if s["kind"] == "handling"]
        assert "HAM" in elements

    def test_reseat_keyword_selects_hag(self, seam_geom):
        reseat_op = next(o for o in seam_geom["seam_operations"]
                         if o["operation"] == "Topstitch cuff edge")
        op = sl.build_seam_operation(reseat_op, "M")
        elements = [s["element"] for s in op.steps if s["kind"] == "handling"]
        assert "HAG" in elements
        assert "HAM" not in elements

    def test_placket_form_gets_fold_step(self, seam_geom):
        placket_op = next(o for o in seam_geom["seam_operations"]
                          if o["operation"] == "Form + stitch front placket (button side)")
        op = sl.build_seam_operation(placket_op, "M")
        elements = [s["element"] for s in op.steps if s["kind"] == "handling"]
        assert "HFC" in elements

    def test_cycle_operation_reposition_step_only_when_count_gt_1(self, seam_geom):
        multi = next(o for o in seam_geom["cycle_operations"]
                    if o["operation"] == "Buttonhole, front placket")   # count=6 at size M
        op_multi = sl.build_cycle_operation(multi, "M")
        elements_multi = [s["element"] for s in op_multi.steps if s["kind"] == "handling"]
        assert "HRP" in elements_multi

        single = next(o for o in seam_geom["cycle_operations"]
                     if o["operation"] == "Buttonhole, collar band")    # count=1 at size M
        op_single = sl.build_cycle_operation(single, "M")
        elements_single = [s["element"] for s in op_single.steps if s["kind"] == "handling"]
        assert "HRP" not in elements_single

    def test_cycle_operation_count_matches_size_dict(self, seam_geom):
        spec = next(o for o in seam_geom["cycle_operations"]
                   if o["operation"] == "Buttonhole, front placket")
        op_s = sl.build_cycle_operation(spec, "S")
        op_l = sl.build_cycle_operation(spec, "L")
        cycle_step_s = next(s for s in op_s.steps if s["kind"] == "cycle")
        cycle_step_l = next(s for s in op_l.steps if s["kind"] == "cycle")
        assert cycle_step_s["count"] == spec["count"]["S"]
        assert cycle_step_l["count"] == spec["count"]["L"]
        assert cycle_step_s["count"] != cycle_step_l["count"]   # S=6, L=7 per seam_geometry.json


# --------------------------------------------------------------------------
# build_style_operations / style_smv (variant logic)
# --------------------------------------------------------------------------

class TestStyleVariants:
    def test_classic_covers_all_seam_and_cycle_geometry_records(self, seam_geom):
        ops = sl.build_style_operations(seam_geom, "M", "CLASSIC")
        assert len(ops) == len(seam_geom["seam_operations"]) + len(seam_geom["cycle_operations"])

    def test_short_sleeve_drops_cuff_and_gauntlet_ops(self, seam_geom):
        ops = sl.build_style_operations(seam_geom, "M", "SHORT_SLEEVE")
        names = {op.name for op in ops}
        assert not any("cuff" in n.lower() for n in names)
        assert not any("gauntlet" in n.lower() for n in names)
        assert any("hem short sleeve" in n.lower() for n in names)

    def test_blouse_drops_collar_and_band_ops(self, seam_geom):
        ops = sl.build_style_operations(seam_geom, "M", "BLOUSE_COLLARLESS")
        names = {op.name for op in ops}
        assert not any("collar" in n.lower() and "neckline" not in n.lower() for n in names)
        assert any("neckline" in n.lower() for n in names)

    def test_unknown_variant_raises(self, seam_geom):
        with pytest.raises(ValueError):
            sl.build_style_operations(seam_geom, "M", "NOT_A_VARIANT")

    def test_style_smv_positive_and_reasonable(self, seam_geom):
        for variant in ("CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"):
            result = sl.style_smv(seam_geom, "M", variant)
            assert 3.0 < result["SMV_min"] < 40.0, f"{variant} SMV {result['SMV_min']} out of plausible range"

    def test_variant_ordering_short_sleeve_and_blouse_cheaper_than_classic(self, seam_geom):
        classic = sl.style_smv(seam_geom, "M", "CLASSIC")["SMV_min"]
        short = sl.style_smv(seam_geom, "M", "SHORT_SLEEVE")["SMV_min"]
        blouse = sl.style_smv(seam_geom, "M", "BLOUSE_COLLARLESS")["SMV_min"]
        assert short < classic
        assert blouse < classic

    def test_smv_monotonic_nondecreasing_with_size(self, seam_geom):
        for variant in ("CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"):
            smvs = [sl.style_smv(seam_geom, sz, variant)["SMV_min"] for sz in sl.SIZES]
            assert all(a <= b + 1e-6 for a, b in zip(smvs, smvs[1:])), f"{variant}: {smvs}"

    def test_no_double_count_warnings_across_all_variants_and_sizes(self, seam_geom):
        for variant in ("CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"):
            for size in sl.SIZES:
                result = sl.style_smv(seam_geom, size, variant)
                assert result["all_warnings"] == [], f"{variant}/{size}: {result['all_warnings']}"


# --------------------------------------------------------------------------
# validate_shirt_library.py
# --------------------------------------------------------------------------

class TestValidation:
    def test_geometry_crosscheck_matches(self, seam_geom):
        """The stitch-path totals this module recomputes must match
        seam_geometry.json's own stored total exactly -- this is a pure
        geometry read, independent of any MotionParams coefficient."""
        cc = vsl.crosscheck_machine_time(seam_geom, "M")
        assert cc["geometry_match"], cc

    def test_crosscheck_returns_well_formed_result_even_when_minutes_disagree(self, seam_geom):
        """coefficients_match is allowed to be False -- the stored
        machine_time_crosscheck minutes do not currently match this bundle's
        recomputation, and the root cause is UNRESOLVED (see
        crosscheck_machine_time's docstring; an earlier claim that this was
        explained by a MotionParams coefficient change was checked and found
        false). This test only asserts the function still returns a
        well-formed result and does not assert -- and must not be changed to
        assert -- any particular explanation for the gap."""
        cc = vsl.crosscheck_machine_time(seam_geom, "M")
        assert isinstance(cc["coefficients_match"], bool)
        assert "recomputed" in cc and "stored" in cc

    def test_garment_level_comparison_flags_product_mismatch(self, seam_geom, tmp_path):
        bm_path = tmp_path / "bm.csv"
        pd.DataFrame([
            {"company": "TestCo", "assembly_class": "Collar", "method_GSD_s": 48.0, "method_SAM_s": 70.0},
        ]).to_csv(bm_path, index=False)
        df = vsl.garment_level_comparison(seam_geom, str(bm_path))
        assert "DIFFERENT PRODUCT" in df["product"].iloc[0]
        assert df["our_woven_shirt_SMV_min"].iloc[0] > 0

    def test_variant_comparison_table_shape(self, seam_geom):
        df = vsl.variant_comparison_table(seam_geom)
        assert len(df) == 3 * len(sl.SIZES)
        assert set(df["variant"].unique()) == {"CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"}


# --------------------------------------------------------------------------
# IP-provenance smoke check
# --------------------------------------------------------------------------

class TestIPProvenance:
    def test_no_hardcoded_gsd_or_mtm_tables(self):
        for fname in ("shirt_library.py", "validate_shirt_library.py"):
            src = open(fname).read()
            assert "TMU_BY_DISTANCE" not in src
            assert "GB1" not in src and "GB2" not in src
