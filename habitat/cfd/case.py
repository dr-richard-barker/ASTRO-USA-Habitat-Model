"""T2 CFD tier: build an OpenFOAM case for the FPM living volume from the parts registry.

    uv run python -m habitat.cfd.case --mesh coarse [--run] [--np 4]

Physics (M0 smoke configuration; review-amended plan):
  * buoyantSimpleFoam (steady), heRhoThermo + incompressiblePerfectGas, constant properties from
    CoolProp at the set-point; RAS kOmegaSST with wall functions; gravity -z.
  * HVAC loop: supply and return grilles on the attic partition, the SAME mass flow fixed at both
    (flowRateInletVelocity / flowRateOutletVelocity), so the closed room has a steady solution;
    pressure level fixed by pRefPoint/pRefValue.
  * Heat: volumetric sources (fvOptions on h) from the registry; walls adiabatic in M0 (declared).
  * Scalars, all measured RELATIVE TO SUPPLY AIR so steady state exists (review item 1):
      dCO2 [ppm above supply], dH2O [mmol/mol above supply], AoA [s since leaving the supply grille].
    scalarTransport with alphaD/alphaDt (turbulent diffusivity; a constant D is refused, review item 2).
  * Checks written to case_meta.json for post.py: expected heat removal, species return excess and
    the age identity  <AoA>_return,mass-weighted = rho0 * V / mdot.
"""
from __future__ import annotations

import argparse
import itertools
import json
import re
from pathlib import Path

import numpy as np
import trimesh
import CoolProp.CoolProp as CP

from .. import RUNS
from ..registry import Part, build as build_registry
from ..units import to_kg_s
from . import foam
from .foam import Raw, write, write_field

MESH_H_MM = {"coarse": 80.0, "medium": 80.0 / 2 ** 0.5, "fine": 40.0}   # review item 8 (ratio sqrt 2)
OBSTACLE_EXTEND_MM = 25.0     # obstacles touching the domain walls are pushed through them so no faces coincide
SC_LAMINAR, SC_TURB = 0.7, 0.7  # Schmidt numbers for scalar diffusivity (alphaD = 1/Sc); declared modelling choice
FACES = {"xmin": (0, -1), "xmax": (0, 1), "ymin": (1, -1), "ymax": (1, 1), "zmin": (2, -1), "zmax": (2, 1)}
M_CO2 = CP.PropsSI("M", "CO2")      # kg/mol
M_H2O = CP.PropsSI("M", "Water")
M_AIR = CP.PropsSI("M", "Air")


# ----------------------------------------------------------------------------- geometry (mm)
def _face_quads(lo, hi, openings):
    """Box faces split into rectangles; rectangles inside an opening are tagged with its id."""
    cuts = [{lo[a], hi[a]} for a in range(3)]
    for o in openings:
        ax = FACES[o.opening["face"]][0]
        for a in range(3):
            if a != ax:
                cuts[a] |= {o.lo[a], o.hi[a]}
    cuts = [sorted(c) for c in cuts]
    out = []
    for face, (ax, sgn) in FACES.items():
        u, v = [a for a in range(3) if a != ax]
        w = hi[ax] if sgn > 0 else lo[ax]
        for (u0, u1), (v0, v1) in itertools.product(zip(cuts[u][:-1], cuts[u][1:]), zip(cuts[v][:-1], cuts[v][1:])):
            mu, mv = (u0 + u1) / 2, (v0 + v1) / 2
            tag = {"zmin": "floor", "zmax": "ceiling"}.get(face, "walls")
            for o in openings:
                if o.opening["face"] == face and o.lo[u] <= mu <= o.hi[u] and o.lo[v] <= mv <= o.hi[v]:
                    tag = o.id
            q = []
            for uu, vv in ((u0, v0), (u1, v0), (u1, v1), (u0, v1)):
                p = np.zeros(3); p[ax], p[u], p[v] = w, uu, vv
                q.append(p)
            q = np.array(q)
            if np.dot(np.cross(q[1] - q[0], q[2] - q[0]), np.eye(3)[ax] * sgn) < 0:
                q = q[::-1]
            out.append((tag, q))
    return out


def _write_multisolid(path: Path, solids: dict[str, list]):
    with open(path, "w") as f:
        for name, tris in solids.items():
            f.write(f"solid {name}\n")
            for t in tris:
                t = np.asarray(t) / 1000.0
                n = np.cross(t[1] - t[0], t[2] - t[0]); n = n / (np.linalg.norm(n) or 1)
                f.write(f"  facet normal {n[0]:.6e} {n[1]:.6e} {n[2]:.6e}\n    outer loop\n")
                for p in t:
                    f.write(f"      vertex {p[0]:.9e} {p[1]:.9e} {p[2]:.9e}\n")
                f.write("    endloop\n  endfacet\n")
            f.write(f"endsolid {name}\n")


def write_geometry(parts: list[Part], tri: Path) -> dict:
    tri.mkdir(parents=True, exist_ok=True)
    dom = next(p for p in parts if p.cfd_role == "domain")
    lo, hi = np.array(dom.lo), np.array(dom.hi)
    openings = [p for p in parts if p.cfd_role == "opening"]
    solids: dict[str, list] = {}
    for tag, q in _face_quads(lo, hi, openings):
        solids.setdefault(tag, []).extend([q[[0, 1, 2]], q[[0, 2, 3]]])
    _write_multisolid(tri / "domain.stl", solids)
    allt = np.concatenate([np.asarray(t) for t in solids.values()])
    m = trimesh.Trimesh(*trimesh.util.append_faces([allt.reshape(-1, 3)], [np.arange(len(allt) * 3).reshape(-1, 3)]))
    m.merge_vertices()
    vol = float(np.prod(hi - lo))
    assert m.is_watertight and abs(abs(m.volume) - vol) / vol < 1e-6, "domain STL not closed"
    obs: dict[str, list] = {}
    blocked = 0.0
    for p in parts:
        if p.cfd_role != "blockage":
            continue
        plo, phi = np.array(p.lo, float), np.array(p.hi, float)
        clip_lo, clip_hi = np.maximum(plo, lo), np.minimum(phi, hi)
        blocked += float(np.prod(np.clip(clip_hi - clip_lo, 0, None)))
        plo = np.where(np.abs(plo - lo) < 1.0, plo - OBSTACLE_EXTEND_MM, plo)   # push through touching walls
        phi = np.where(np.abs(phi - hi) < 1.0, phi + OBSTACLE_EXTEND_MM, phi)
        b = trimesh.creation.box(extents=phi - plo); b.apply_translation((plo + phi) / 2)
        obs[p.id] = list(b.triangles)
    _write_multisolid(tri / "obstacles.stl", obs)
    return {"domain_volume_m3": vol / 1e9, "blocked_volume_m3": blocked / 1e9,
            "air_volume_nominal_m3": (vol - blocked) / 1e9, "patches": sorted(solids), "obstacles": sorted(obs)}


# ----------------------------------------------------------------------------- case
def s6_tracers(L, parts, h_mm: float) -> tuple[list, dict, dict]:
    """S6 route tracers. Returns (extra zones [(name, lo_m, hi_m)], {route: [(zone, mol_s)]}, info)."""
    P = {p.id: p for p in parts}
    rack, alg = P["payload_bioreactor_rack"], P["payload_photobioreactor"]
    n_tube = to_kg_s(L.num("payloads.bioreactor_rack.co2_per_tube", "g/day"), "g/day") / M_CO2
    half = 0.75 * h_mm
    zones, port_zone = [], {}
    gas = [q for q in rack.ports if q["kind"] == "gas_out"]
    for q in gas:                                          # small box just outside each vessel vent tip
        c = np.array(q["pos"]) + np.array(q["dir"]) * 0.5 * h_mm
        port_zone[q["name"]] = f"port_{q['name']}"
        zones.append((port_zone[q["name"]], (c - half) / 1000, (c + half) / 1000))
    vent = next(q for q in alg.ports if q["name"] == "vent")
    inlet = next(q for q in alg.ports if q["name"] == "gas_in")
    vc = np.array([vent["pos"][0], vent["pos"][1], alg.hi[2] + 1.5 * h_mm + half])  # clear of the photobioreactor's heat shell
    zones.append(("photobioreactor_vent", (vc - half) / 1000, (vc + half) / 1000))
    n_pipe = int(L.num("payloads.photobioreactor.sparge_flow_max", "L/min") // L.num("payloads.bioreactor_rack.vent_flow", "L/min"))
    by_dist = sorted(gas, key=lambda q: np.linalg.norm(np.array(q["pos"]) - np.array(inlet["pos"])))
    piped, vented = by_dist[:n_pipe], by_dist[n_pipe:]
    routes = {}
    for r in L.val("scenario_s6.routes"):
        if r == "bay":
            routes[r] = [(port_zone[q["name"]], n_tube) for q in gas]
        elif r == "photobioreactor":
            routes[r] = [("photobioreactor_vent", n_tube * len(piped))] + [(port_zone[q["name"]], n_tube) for q in vented]
        elif r == "nft_wall":
            routes[r] = [("nft_canopy", n_tube * len(gas))]
        else:
            raise ValueError(f"unknown route {r}")
        tot = sum(m for _, m in routes[r])
        assert abs(tot - n_tube * len(gas)) < 1e-15, f"route {r} releases {tot}, expected {n_tube * len(gas)}"
    info = {"co2_per_tube_mol_s": n_tube, "tubes": len(gas), "piped_to_photobioreactor": [q["name"] for q in piped],
            "vented_when_piped": [q["name"] for q in vented], "sparge_capacity_units": n_pipe}
    return zones, routes, info


def build(mesh: str = "coarse", nprocs: int = 4, tag: str = "", scenario: str = "m0") -> Path:
    L, parts = build_registry(scenario=scenario)
    case = RUNS / f"fpm_{scenario}_{mesh}{tag}"
    tri = case / "constant" / "triSurface"
    geo = write_geometry(parts, tri)
    dom = next(p for p in parts if p.cfd_role == "domain")
    lo, hi = np.array(dom.lo) / 1000, np.array(dom.hi) / 1000
    h = MESH_H_MM[mesh] / 1000

    T0 = L.num("scenario_m0.hvac.setpoint_T", "C") + 273.15
    sup = next(p for p in parts if p.id == "hvac_supply")
    Ts = sup.opening["supply_T_C"] + 273.15
    Q = sup.opening["flow_m3_s"]
    p0 = 101325.0
    props = {k: CP.PropsSI(k2, "T", T0, "P", p0, "Air") for k, k2 in
             (("rho", "D"), ("mu", "V"), ("cp", "C"), ("k", "L"))}
    Pr = props["mu"] * props["cp"] / props["k"]
    R_air = 8.314462618 / M_AIR
    rho_s = p0 / (R_air * Ts)                    # incompressiblePerfectGas density of supply air
    rho0 = p0 / (R_air * T0)
    mdot = rho_s * Q

    # --- background mesh (non-integer margin keeps background faces off STL faces; hwreview a560932)
    margin = 1.37 * h
    blo, bhi = lo - margin, hi + margin
    n = np.maximum(1, np.round((bhi - blo) / h)).astype(int)
    v = [(blo[0], blo[1], blo[2]), (bhi[0], blo[1], blo[2]), (bhi[0], bhi[1], blo[2]), (blo[0], bhi[1], blo[2]),
         (blo[0], blo[1], bhi[2]), (bhi[0], blo[1], bhi[2]), (bhi[0], bhi[1], bhi[2]), (blo[0], bhi[1], bhi[2])]
    write(case / "system" / "blockMeshDict", "dictionary", "blockMeshDict",
          "convertToMeters 1;\nvertices (\n" + "\n".join(f"    ({a:.9g} {b:.9g} {c:.9g})" for a, b, c in v)
          + f"\n);\nblocks ( hex (0 1 2 3 4 5 6 7) ({n[0]} {n[1]} {n[2]}) simpleGrading (1 1 1) );\n"
          "boundary ( background { type patch; faces ((0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2) (0 3 2 1) (4 5 6 7)); } );\n")

    region_level = {"hvac_supply": 2, "hvac_return": 2}
    regions = "\n".join(f"                {r} {{ level ({region_level.get(r, 0)} {region_level.get(r, 0)}); "
                        f"patchInfo {{ type {'patch' if r.startswith('hvac') else 'wall'}; }} }}" for r in geo["patches"])
    obs_regions = "\n".join(f"                {r} {{ level (0 1); patchInfo {{ type wall; }} }}" for r in geo["obstacles"])
    # location in mesh: aisle centre at mid-height, nudged off the cell grid
    loc = np.array([(lo[0] + hi[0]) / 2 + 0.0137, (lo[1] + hi[1]) / 2 + 0.0113, (lo[2] + hi[2]) / 2 + 0.0071])
    write(case / "system" / "snappyHexMeshDict", "dictionary", "snappyHexMeshDict", f"""
castellatedMesh true;
snap            true;
addLayers       false;
geometry
{{
    domain.stl {{ type triSurfaceMesh; name domain; }}
    obstacles.stl {{ type triSurfaceMesh; name obstacles; }}
}};
castellatedMeshControls
{{
    maxLocalCells 4000000; maxGlobalCells 12000000; minRefinementCells 0; maxLoadUnbalance 0.10;
    nCellsBetweenLevels 3;
    features ( {{ file "domain.eMesh"; level 2; }} {{ file "obstacles.eMesh"; level 1; }} );
    refinementSurfaces
    {{
        domain {{ level (0 0); regions {{
{regions}
            }} }}
        obstacles {{ level (0 1); regions {{
{obs_regions}
            }} }}
    }}
    resolveFeatureAngle 30;
    refinementRegions {{ }}
    locationInMesh ({loc[0]:.9g} {loc[1]:.9g} {loc[2]:.9g});
    allowFreeStandingZoneFaces true;
}}
snapControls
{{
    nSmoothPatch 3; tolerance 2.0; nSolveIter 50; nRelaxIter 5;
    nFeatureSnapIter 10; implicitFeatureSnap false; explicitFeatureSnap true; multiRegionFeatureSnap true;
}}
addLayersControls
{{
    relativeSizes true; layers {{ }} expansionRatio 1.2; finalLayerThickness 0.3; minThickness 0.1;
    nGrow 0; featureAngle 60; nRelaxIter 3; nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
    maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3; minMedialAxisAngle 90; nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}
meshQualityControls
{{
    maxNonOrtho 65; maxBoundarySkewness 20; maxInternalSkewness 4; maxConcave 80; minVol 1e-16;
    minTetQuality 1e-15; minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.05;
    minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
    relaxed {{ maxNonOrtho 75; }}
}}
mergeTolerance 1e-6;
""")
    # obstacle edges pushed outside the walls must not become snapping features (they dragged wall
    # points 25 mm outward in the first M0 mesh), so obstacle features are clipped to the domain box
    clip = f"insideBox ({lo[0]:.9g} {lo[1]:.9g} {lo[2]:.9g}) ({hi[0]:.9g} {hi[1]:.9g} {hi[2]:.9g});"
    write(case / "system" / "surfaceFeatureExtractDict", "dictionary", "surfaceFeatureExtractDict",
          "".join(f"{s}\n{{\n    extractionMethod extractFromSurface;\n    includedAngle 150;\n"
                  f"    subsetFeatures {{ nonManifoldEdges no; openEdges yes; {clip if s == 'obstacles.stl' else ''} }}\n"
                  "    writeObj no;\n}\n" for s in ("domain.stl", "obstacles.stl")))

    # --- source cellZones. Heated blockages have no cells inside them, so their heat goes into a
    # one-cell-thick fluid shell around them (box grown by h; the solid interior is not meshed).
    zones = [p for p in parts if p.cfd_role == "source_zone"]
    shells = [p for p in parts if p.cfd_role == "blockage" and (p.heat_W or p.co2_kg_s or p.h2o_kg_s)]
    acts = []
    for z in zones + shells:
        grow = h * 1000 if z in shells else 0.0
        a, b = (np.array(z.lo) - grow) / 1000, (np.array(z.hi) + grow) / 1000
        acts.append(f"    {{ name {z.id}; type cellZoneSet; action new; source boxToCell; "
                    f"box ({a[0]:.9g} {a[1]:.9g} {a[2]:.9g}) ({b[0]:.9g} {b[1]:.9g} {b[2]:.9g}); }}")
    tracer_zones, tracers, tracer_info = (s6_tracers(L, parts, MESH_H_MM[mesh]) if scenario == "s6" else ([], {}, {}))
    for nm, a, b in tracer_zones:
        acts.append(f"    {{ name {nm}; type cellZoneSet; action new; source boxToCell; "
                    f"box ({a[0]:.9g} {a[1]:.9g} {a[2]:.9g}) ({b[0]:.9g} {b[1]:.9g} {b[2]:.9g}); }}")
    write(case / "system" / "topoSetDict", "dictionary", "topoSetDict", "actions\n(\n" + "\n".join(acts) + "\n);\n")

    # --- thermophysics / turbulence / gravity
    write(case / "constant" / "thermophysicalProperties", "dictionary", "thermophysicalProperties", {
        "thermoType": {"type": "heRhoThermo", "mixture": "pureMixture", "transport": "const", "thermo": "hConst",
                       "equationOfState": "incompressiblePerfectGas", "specie": "specie",
                       "energy": "sensibleEnthalpy"},
        "mixture": {"specie": {"molWeight": M_AIR * 1000}, "equationOfState": {"pRef": p0},
                    "thermodynamics": {"Cp": props["cp"], "Hf": 0}, "transport": {"mu": props["mu"], "Pr": Pr}}})
    write(case / "constant" / "turbulenceProperties", "dictionary", "turbulenceProperties",
          {"simulationType": "RAS", "RAS": {"RASModel": "kOmegaSST", "turbulence": "on", "printCoeffs": "on"}})
    write(case / "constant" / "g", "uniformDimensionedVectorField", "g",
          "dimensions [0 1 -2 0 0 0 0];\nvalue (0 0 -9.80665);\n")

    # --- heat sources (W into h) and species/age sources
    fv_h, fv_s = {}, {"dCO2": {}, "dH2O": {}}
    src_tot = {"heat_W": 0.0, "co2_mol_s": 0.0, "h2o_mol_s": 0.0}
    for z in zones + shells:
        if z.heat_W:
            fv_h[f"heat_{z.id}"] = {"type": "scalarSemiImplicitSource", "selectionMode": "cellZone", "cellZone": z.id,
                                    "volumeMode": "absolute", "sources": {"h": {"explicit": z.heat_W, "implicit": 0}}}
            src_tot["heat_W"] += z.heat_W
        if z.co2_kg_s:
            nco2 = z.co2_kg_s / M_CO2
            src_tot["co2_mol_s"] += nco2
            fv_s["dCO2"][f"co2_{z.id}"] = {"type": "scalarSemiImplicitSource", "selectionMode": "cellZone",
                                          "cellZone": z.id, "volumeMode": "absolute",
                                          "sources": {"dCO2": {"explicit": nco2 * M_AIR * 1e6, "implicit": 0}}}
        if z.h2o_kg_s:
            nh2o = z.h2o_kg_s / M_H2O
            src_tot["h2o_mol_s"] += nh2o
            fv_s["dH2O"][f"h2o_{z.id}"] = {"type": "scalarSemiImplicitSource", "selectionMode": "cellZone",
                                          "cellZone": z.id, "volumeMode": "absolute",
                                          "sources": {"dH2O": {"explicit": nh2o * M_AIR * 1e3, "implicit": 0}}}
    # every watt / mole in the registry must reach the case (a dropped source would still "balance")
    want = {"heat_W": sum(p.heat_W for p in parts), "co2_mol_s": sum(p.co2_kg_s for p in parts) / M_CO2,
            "h2o_mol_s": sum(p.h2o_kg_s for p in parts) / M_H2O}
    for key, w in want.items():
        assert abs(src_tot[key] - w) <= 1e-9 * max(1.0, abs(w)), f"source {key}: case {src_tot[key]} != registry {w}"
    write(case / "constant" / "fvOptions", "dictionary", "fvOptions", fv_h)

    # --- fields
    pat = [f"domain_{r}" for r in geo["patches"]] + [f"obstacles_{r}" for r in geo["obstacles"]]
    a_sup = (sup.hi[1] - sup.lo[1]) * (sup.hi[2] - sup.lo[2]) / 1e6          # grille area, m2
    kin = 1.5 * (0.05 * Q / a_sup) ** 2     # 5 % intensity at the supply face velocity (initial value only)
    U, prgh, p, T, k, om, nut, at = {}, {}, {}, {}, {}, {}, {}, {}
    TR = [f"tr_{r}" for r in tracers]
    S = {s: {} for s in ("dCO2", "dH2O", "AoA", *TR)}
    for pf in pat:
        p[pf] = {"type": "calculated", "value": f"uniform {p0}"}
        nut[pf] = {"type": "nutkWallFunction", "value": "uniform 0"}
        at[pf] = {"type": "compressible::alphatWallFunction", "Prt": 0.85, "value": "uniform 0"}
        prgh[pf] = {"type": "fixedFluxPressure", "value": f"uniform {p0}"}
        if pf == "domain_hvac_supply":
            U[pf] = {"type": "flowRateInletVelocity", "massFlowRate": mdot, "rhoInlet": rho_s, "value": "uniform (0 0 0)"}
            T[pf] = {"type": "fixedValue", "value": f"uniform {Ts}"}
            k[pf] = {"type": "turbulentIntensityKineticEnergyInlet", "intensity": 0.05, "value": f"uniform {kin}"}
            om[pf] = {"type": "turbulentMixingLengthFrequencyInlet", "mixingLength": 0.01, "value": "uniform 1"}
            nut[pf] = {"type": "calculated", "value": "uniform 0"}
            at[pf] = {"type": "calculated", "value": "uniform 0"}
            for s in S:
                S[s][pf] = {"type": "fixedValue", "value": "uniform 0"}
        elif pf == "domain_hvac_return":
            U[pf] = {"type": "flowRateOutletVelocity", "massFlowRate": mdot, "rhoOutlet": rho0, "value": "uniform (0 0 0)"}
            T[pf] = {"type": "inletOutlet", "inletValue": f"uniform {T0}", "value": f"uniform {T0}"}
            k[pf] = {"type": "inletOutlet", "inletValue": f"uniform {kin}", "value": f"uniform {kin}"}
            om[pf] = {"type": "inletOutlet", "inletValue": "uniform 1", "value": "uniform 1"}
            nut[pf] = {"type": "calculated", "value": "uniform 0"}
            at[pf] = {"type": "calculated", "value": "uniform 0"}
            for s in S:
                S[s][pf] = {"type": "inletOutlet", "inletValue": "uniform 0", "value": "uniform 0"}
        else:
            U[pf] = {"type": "noSlip"}
            T[pf] = {"type": "zeroGradient"}                      # adiabatic (scenario_m0.walls_adiabatic)
            k[pf] = {"type": "kqRWallFunction", "value": f"uniform {kin}"}
            om[pf] = {"type": "omegaWallFunction", "value": "uniform 1"}
            for s in S:
                S[s][pf] = {"type": "zeroGradient"}
    write_field(case, "U", "[0 1 -1 0 0 0 0]", "uniform (0 0 0)", U, cls="volVectorField")
    write_field(case, "p", "[1 -1 -2 0 0 0 0]", f"uniform {p0}", p)
    write_field(case, "p_rgh", "[1 -1 -2 0 0 0 0]", f"uniform {p0}", prgh)
    # initial room temperature = energy-balanced return temperature (supply + sources / (mdot cp)). The steady
    # answer does not depend on it, but starting at the set-point left the room-mean temperature as a very slow
    # mode: run1 was still 1.8 K high after 3000 iterations (results/cfd/fpm_m0_coarse_run1_*).
    T_init = Ts + sum(p.heat_W for p in parts) / (mdot * props["cp"])
    write_field(case, "T", "[0 0 0 1 0 0 0]", f"uniform {T_init}", T)
    write_field(case, "k", "[0 2 -2 0 0 0 0]", f"uniform {kin}", k)
    write_field(case, "omega", "[0 0 -1 0 0 0 0]", "uniform 1", om)
    write_field(case, "nut", "[0 2 -1 0 0 0 0]", "uniform 0", nut)
    write_field(case, "alphat", "[1 -1 -1 0 0 0 0]", "uniform 0", at)
    for s in S:
        write_field(case, s, "[0 0 0 0 0 0 0]", "uniform 0", S[s])

    # --- function objects
    funcs = {}
    for s in ("dCO2", "dH2O"):
        fo = {"type": "scalarTransport", "libs": '("libsolverFunctionObjects.so")', "field": s,
              "alphaD": 1 / SC_LAMINAR, "alphaDt": 1 / SC_TURB, "nCorr": 1, "writeControl": "writeTime"}
        if fv_s[s]:
            fo["fvOptions"] = fv_s[s]
        funcs[f"transport_{s}"] = fo
    # age of air: rho-weighted equation, specific source rho0 (kg m-3 s/s) -> identity <AoA>_out = rho0 V / mdot
    funcs["transport_AoA"] = {"type": "scalarTransport", "libs": '("libsolverFunctionObjects.so")', "field": "AoA",
                              "alphaD": 1 / SC_LAMINAR, "alphaDt": 1 / SC_TURB, "nCorr": 1, "writeControl": "writeTime",
                              "fvOptions": {"age": {"type": "scalarSemiImplicitSource", "selectionMode": "all",
                                                    "volumeMode": "specific",
                                                    "sources": {"AoA": {"explicit": rho0, "implicit": 0}}}}}
    for r, srcs in tracers.items():
        fo = {"type": "scalarTransport", "libs": '("libsolverFunctionObjects.so")', "field": f"tr_{r}",
              "alphaD": 1 / SC_LAMINAR, "alphaDt": 1 / SC_TURB, "nCorr": 1, "writeControl": "writeTime",
              "fvOptions": {f"src_{r}_{k}": {"type": "scalarSemiImplicitSource", "selectionMode": "cellZone",
                                             "cellZone": zn, "volumeMode": "absolute",
                                             "sources": {f"tr_{r}": {"explicit": mol * M_AIR * 1e6, "implicit": 0}}}
                            for k, (zn, mol) in enumerate(srcs)}}
        funcs[f"transport_tr_{r}"] = fo
    every = 20
    scal_all = "(T dCO2 dH2O AoA " + " ".join(TR) + ")"
    probes = {}
    if scenario == "s6":
        P = {p.id: p for p in parts}
        hm = MESH_H_MM[mesh]
        for p in parts:
            if p.layer == "crew":
                probes[f"{p.id}_head"] = [(p.lo[0] + p.hi[0]) / 2, (p.lo[1] + p.hi[1]) / 2, p.hi[2] - hm]
        for pid, port in (("payload_incubator", "intake_fan"), ("payload_sensor_module", "sample_membrane")):
            q = next(q for q in P[pid].ports if q["name"] == port)
            probes[f"{pid.replace('payload_', '')}_{port}"] = [q["pos"][0], q["pos"][1], P[pid].hi[2] + 0.75 * hm]
        can = P["nft_canopy"]
        for k, f in enumerate((0.15, 0.5, 0.85)):
            probes[f"nft_canopy_{k}"] = [can.lo[0] + f * (can.hi[0] - can.lo[0]), (can.lo[1] + can.hi[1]) / 2,
                                          (can.lo[2] + can.hi[2]) / 2]
        bay = P["myco_enclosure"]
        probes["bay_centre"] = [(bay.lo[0] + bay.hi[0]) / 2, (bay.lo[1] + bay.hi[1]) / 2, bay.hi[2] * 0.75]
        funcs["probes"] = {"type": "probes", "libs": '("libsampling.so")', "writeControl": "timeStep",
                           "writeInterval": every, "fields": scal_all,
                           "probeLocations": Raw("(" + " ".join(f"({x / 1000:.6g} {y / 1000:.6g} {z / 1000:.6g})"
                                                                for x, y, z in probes.values()) + ")")}
        for zn in ("nft_canopy", "crew_1", "crew_2", "workbench_zone"):
            funcs[f"zone_{zn}"] = {"type": "volFieldValue", "libs": '("libfieldFunctionObjects.so")',
                                   "writeControl": "timeStep", "writeInterval": every, "writeFields": "false",
                                   "regionType": "cellZone", "name": zn, "operation": "volAverage", "fields": scal_all}
    for o in ("hvac_supply", "hvac_return"):
        funcs[f"flux_{o}"] = {"type": "surfaceFieldValue", "libs": '("libfieldFunctionObjects.so")',
                              "writeControl": "timeStep", "writeInterval": every, "writeFields": "false",
                              "regionType": "patch", "name": f"domain_{o}", "operation": "weightedAverage",
                              "weightField": "phi", "fields": scal_all}
        funcs[f"mflow_{o}"] = {"type": "surfaceFieldValue", "libs": '("libfieldFunctionObjects.so")',
                               "writeControl": "timeStep", "writeInterval": every, "writeFields": "false",
                               "regionType": "patch", "name": f"domain_{o}", "operation": "sum", "fields": "(phi)"}
    funcs["volAvg"] = {"type": "volFieldValue", "libs": '("libfieldFunctionObjects.so")', "writeControl": "timeStep",
                       "writeInterval": every, "writeFields": "false", "regionType": "all", "operation": "volAverage",
                       "fields": scal_all}
    funcs["residuals"] = {"type": "solverInfo", "libs": '("libutilityFunctionObjects.so")', "fields": "(U h p_rgh k omega)"}
    write(case / "system" / "controlDict", "dictionary", "controlDict", {
        "application": "buoyantSimpleFoam", "startFrom": "latestTime", "startTime": 0, "stopAt": "endTime",
        "endTime": 4000, "deltaT": 1, "writeControl": "timeStep", "writeInterval": 500, "purgeWrite": 2,
        "writeFormat": "binary", "writePrecision": 8, "writeCompression": "off", "timeFormat": "general",
        "timePrecision": 6, "runTimeModifiable": "true", "functions": funcs})
    write(case / "system" / "fvSchemes", "dictionary", "fvSchemes", {
        "ddtSchemes": {"default": "steadyState"},
        "gradSchemes": {"default": "Gauss linear"},
        "divSchemes": {"default": "none", "div(phi,U)": "bounded Gauss linearUpwind grad(U)",
                       "div(phi,h)": "bounded Gauss linearUpwind grad(h)", "div(phi,K)": "bounded Gauss upwind",
                       "div(phi,k)": "bounded Gauss upwind", "div(phi,omega)": "bounded Gauss upwind",
                       "div(phi,dCO2)": "bounded Gauss limitedLinear 1", "div(phi,dH2O)": "bounded Gauss limitedLinear 1",
                       "div(phi,AoA)": "bounded Gauss limitedLinear 1",
                       **{f"div(phi,{t})": "bounded Gauss limitedLinear 1" for t in TR},
                       "div(((rho*nuEff)*dev2(T(grad(U)))))": "Gauss linear"},
        "laplacianSchemes": {"default": "Gauss linear limited corrected 0.33"},
        "interpolationSchemes": {"default": "linear"},
        "snGradSchemes": {"default": "limited corrected 0.33"},
        "wallDist": {"method": "meshWave"}})
    write(case / "system" / "fvSolution", "dictionary", "fvSolution", {
        "solvers": {
            "p_rgh": {"solver": "GAMG", "smoother": "DIC", "tolerance": 1e-7, "relTol": 0.01},
            "\"(U|h|k|omega)\"": {"solver": "smoothSolver", "smoother": "symGaussSeidel", "tolerance": 1e-8,
                                  "relTol": 0.1},
            # steady scalars: Gauss-Seidel smoother (PBiCGStab broke down with a SIGFPE on dH2O in run2)
            "\"(dCO2|dH2O|AoA|tr_.*)\"": {"solver": "smoothSolver", "smoother": "GaussSeidel", "nSweeps": 2,
                                    "tolerance": 1e-9, "relTol": 0.05, "maxIter": 100}},
        "SIMPLE": {"momentumPredictor": "no", "nNonOrthogonalCorrectors": 0,
                   "pRefPoint": Raw(f"({loc[0]:.6g} {loc[1]:.6g} {loc[2]:.6g})"), "pRefValue": p0},
        "relaxationFactors": {"fields": {"rho": 1.0, "p_rgh": 0.7},
                              "equations": {"U": 0.3, "h": 0.5, "\"(k|omega)\"": 0.5,
                                            "\"(dCO2|dH2O|AoA|tr_.*)\"": 0.9}}})
    write(case / "system" / "decomposeParDict", "dictionary", "decomposeParDict",
          {"numberOfSubdomains": nprocs, "method": "scotch"})

    meta = {"case": case.name, "scenario": scenario, "mesh": mesh,
            "tracers": {r: [{"zone": z, "mol_s": m} for z, m in v] for r, v in tracers.items()},
            "tracer_info": tracer_info, "probes": probes, "cell_mm": MESH_H_MM[mesh], "background_cells": int(np.prod(n)),
            "domain_bounds_m": [lo.tolist(), hi.tolist()],
            "ledger_digest": L.digest(), "geometry": geo,
            "physics": {"T0_K": T0, "supply_T_K": Ts, "Q_m3_s": Q, "mdot_kg_s": mdot, "rho0": rho0, "rho_supply": rho_s,
                        "cp": props["cp"], "mu": props["mu"], "Pr": Pr, "M_air": M_AIR, "Sc": SC_LAMINAR,
                        "Sc_t": SC_TURB, "property_source": "CoolProp (Lemmon et al. 2000 air EOS)"},
            "sources_total": src_tot,
            "expected": {
                "return_T_rise_K": src_tot["heat_W"] / (mdot * props["cp"]),
                "return_dCO2_ppm": src_tot["co2_mol_s"] * M_AIR / mdot * 1e6,
                "return_dH2O_mmol_mol": src_tot["h2o_mol_s"] * M_AIR / mdot * 1e3,
                "age_identity": "flux-weighted AoA at return = rho0 * V_mesh / mdot (V_mesh from checkMesh)"},
            "parts": [{"id": z.id, "heat_W": z.heat_W, "co2_kg_s": z.co2_kg_s, "h2o_kg_s": z.h2o_kg_s, "digest": z.digest(),
                       "applied_as": "shell" if z in shells else "zone"} for z in zones + shells],
            "ledger_used": L.usage_report()}
    (case / "case_meta.json").write_text(json.dumps(meta, indent=1, default=str))
    return case


def mesh_case(case: Path):
    foam.run(case, ["blockMesh", "surfaceFeatureExtract", "snappyHexMesh -overwrite", "checkMesh", "topoSet"])
    log = (case / "log.checkMesh").read_text()
    bb = re.search(r"Overall domain bounding box \(([^)]+)\) \(([^)]+)\)", log)
    meta = json.loads((case / "case_meta.json").read_text())
    want = np.array(meta["domain_bounds_m"])
    got = np.array([[float(x) for x in bb.group(1).split()], [float(x) for x in bb.group(2).split()]])
    if np.abs(got - want).max() > 1e-3:
        raise foam.FoamError(f"{case.name}: mesh extends beyond the domain: {got.tolist()} vs {want.tolist()}")
    if "Mesh OK" not in log:
        raise foam.FoamError(f"{case.name}: checkMesh did not report 'Mesh OK':\n" +
                             "\n".join([ln for ln in log.splitlines() if "***" in ln][:10]))


def solve(case: Path, nprocs: int = 4):
    if nprocs > 1:
        foam.run(case, ["decomposePar -force", f"par:buoyantSimpleFoam", "reconstructPar -latestTime"], nprocs=nprocs)
    else:
        foam.run(case, ["buoyantSimpleFoam"])


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--mesh", choices=list(MESH_H_MM), default="coarse")
    ap.add_argument("--np", type=int, default=4)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--mesh-only", action="store_true")
    ap.add_argument("--scenario", choices=["m0", "s6"], default="m0")
    a = ap.parse_args(argv)
    case = build(a.mesh, a.np, scenario=a.scenario)
    print(case)
    if a.run or a.mesh_only:
        mesh_case(case)
    if a.run:
        solve(case, a.np)


if __name__ == "__main__":
    main()
