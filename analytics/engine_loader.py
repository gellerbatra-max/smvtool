"""
engine_loader.py -- path-independent bootstrap for the SMV calculation engine.

The engine modules (handling_time.py / machine_time.py / allowance.py /
smv_assembly.py / shirt_library.py) are an unpackaged set of flat modules
that import each other by bare name (`import handling_time as ht`) and, in
shirt_library.style_smv()'s case, load their JSON/CSV source data with
*hardcoded* bare filenames (`"element_taxonomy.json"`, relative to the
process's current working directory). That is a pre-existing constraint of
the engine bundle, not something this analytics layer re-implements or
patches -- see INTEGRATION.md for exactly how a backend must run this code
(either with cwd = the engine bundle directory, or with the bundle's data
files copied/symlinked into cwd).

This module only adds the engine bundle directory to `sys.path` once (so its
modules import), and provides `load_engine_context()` for callers (chiefly
what_if.py) who need direct handles on the taxonomy/machine-catalog/
allowance-policy objects rather than going through shirt_library.style_smv().

Public API
----------
    ensure_engine_on_path(engine_dir) -> None
    load_engine_context(engine_dir) -> EngineContext(tax, mcat, pol, sa, sl)
"""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any


def ensure_engine_on_path(engine_dir: str) -> None:
    """Idempotently add `engine_dir` to sys.path so the flat engine modules
    (which import each other by bare name) can be imported from anywhere."""
    engine_dir = os.path.abspath(engine_dir)
    if engine_dir not in sys.path:
        sys.path.insert(0, engine_dir)


@dataclass
class EngineContext:
    engine_dir: str
    tax: Any        # handling_time.Taxonomy
    mcat: Any       # machine_time.MachineCatalog
    pol: Any        # allowance.AllowancePolicy
    ht: Any         # handling_time module
    mt: Any         # machine_time module
    al: Any         # allowance module
    sa: Any         # smv_assembly module
    sl: Any         # shirt_library module


def load_engine_context(engine_dir: str) -> EngineContext:
    """Import the engine modules and load its three source-data catalogs
    (taxonomy, machine catalog, allowance policy) from `engine_dir`,
    returning handles the analytics layer can pass straight into
    smv_assembly.assemble_operation / assemble_style.

    Never hardcodes any GSD/MTM/PMTS lookup value here -- this only wires up
    the engine's own loaders against its own bundled source-data files.
    """
    ensure_engine_on_path(engine_dir)
    import handling_time as ht
    import machine_time as mt
    import allowance as al
    import smv_assembly as sa
    import shirt_library as sl

    tax = ht.load_taxonomy(os.path.join(engine_dir, "element_taxonomy.json"))
    mcat = mt.load_machine_catalog(os.path.join(engine_dir, "machine_classes.csv"))
    pol = al.load_allowance_policy(os.path.join(engine_dir, "allowance_policy.json"))
    return EngineContext(engine_dir=engine_dir, tax=tax, mcat=mcat, pol=pol,
                          ht=ht, mt=mt, al=al, sa=sa, sl=sl)


def build_and_assemble_style(ctx: EngineContext, seam_geom: dict, size: str,
                              variant: str = "CLASSIC", bundle_size: "int | None" = None,
                              allowance_profile: str = "WOVEN_TOPS_DECOMPOSED"):
    """Path-independent equivalent of `shirt_library.style_smv()`.

    `shirt_library.style_smv()` itself re-loads the taxonomy/machine-catalog/
    allowance-policy from hardcoded bare filenames every call (so it only
    works with cwd = the engine bundle directory). `build_style_operations()`
    has no such constraint -- it only consumes the `seam_geom` dict already
    passed in -- so this helper builds the operation list via
    `shirt_library.build_style_operations()` and assembles it against the
    already-loaded `EngineContext`, giving the exact same numbers as
    `style_smv()` without the cwd dependency. Returns
    `(operations: list[sa.Operation], assembled_style: dict)` -- the
    operations list is what `what_if.py` needs to locate and mutate a single
    step; the assembled dict is the same shape `smv_assembly.assemble_style()`
    always returns.
    """
    kwargs = {}
    if bundle_size is not None:
        kwargs["bundle_size"] = bundle_size
    operations = ctx.sl.build_style_operations(seam_geom, size, variant, **kwargs)
    assembled = ctx.sa.assemble_style(ctx.tax, ctx.mcat, ctx.pol, operations,
                                       allowance_profile=allowance_profile)
    return operations, assembled
