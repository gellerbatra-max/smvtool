"""
Shared pytest fixtures for the analytics test suite.

The analytics package (line_balancing.py / costing.py / what_if.py /
engine_loader.py) does not vendor the SMV calculation engine -- it imports
it at runtime from wherever it is unpacked. Point these tests at the engine
bundle via the `SMV_ENGINE_DIR` environment variable; if unset, a handful of
common relative locations are tried (this analytics package is expected to
sit either next to an `engine/smv_engine_bundle/` checkout, or directly
alongside the unzipped `smv_engine_bundle/` contents).
"""
import json
import os
import sys

import pytest

_CANDIDATE_RELATIVE_DIRS = [
    "../../engine/smv_engine_bundle",  # this build's own layout: <root>/analytics, <root>/engine/smv_engine_bundle
    "../../smv_engine_bundle",         # analytics/ and smv_engine_bundle/ as siblings
    "../smv_engine_bundle",            # smv_engine_bundle/ nested inside analytics/
    "..",                              # analytics/ dropped inside the unpacked bundle itself
]


def _discover_engine_dir() -> str:
    env = os.environ.get("SMV_ENGINE_DIR")
    if env:
        if not os.path.isfile(os.path.join(env, "element_taxonomy.json")):
            raise RuntimeError(f"SMV_ENGINE_DIR={env!r} does not contain element_taxonomy.json")
        return os.path.abspath(env)
    here = os.path.dirname(os.path.abspath(__file__))
    for rel in _CANDIDATE_RELATIVE_DIRS:
        cand = os.path.abspath(os.path.join(here, rel))
        if os.path.isfile(os.path.join(cand, "element_taxonomy.json")):
            return cand
    raise RuntimeError(
        "Could not locate the SMV engine bundle. Set SMV_ENGINE_DIR to the "
        "directory containing element_taxonomy.json / machine_classes.csv / "
        "allowance_policy.json / handling_time.py etc.")


ENGINE_DIR = _discover_engine_dir()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")  # analytics/ itself
import engine_loader as el  # noqa: E402


@pytest.fixture(scope="session")
def engine_dir():
    return ENGINE_DIR


@pytest.fixture(scope="session")
def ctx(engine_dir):
    return el.load_engine_context(engine_dir)


@pytest.fixture(scope="session")
def seam_geom(engine_dir):
    with open(os.path.join(engine_dir, "seam_geometry.json")) as fh:
        return json.load(fh)


@pytest.fixture(params=["CLASSIC", "SHORT_SLEEVE", "BLOUSE_COLLARLESS"])
def variant(request):
    return request.param


@pytest.fixture(params=["S", "M", "L", "XL", "XXL"])
def size(request):
    return request.param


@pytest.fixture
def classic_m(ctx, seam_geom):
    """The style used throughout the DEMO and as the most-exercised fixture:
    CLASSIC woven shirt, size M."""
    ops, style = el.build_and_assemble_style(ctx, seam_geom, "M", "CLASSIC")
    return ops, style
