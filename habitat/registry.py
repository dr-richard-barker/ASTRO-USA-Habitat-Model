"""Parts registry: one list of parts, built only from ledger values, shared by CAD, CFD and VR.

Model frame (mm, right-handed, z up):
  x — along the 464 in length, from the door end (printed left of Fig 2) toward the attic;
  y — across the 92 in width, from the printed BOTTOM wall of Fig 2 (battery / work-space side)
      toward the printed TOP wall (hydroponics / Mycoponics wall): y_model = width - y_fig;
  z — up from the floor.

No dimension is typed in this file: every number comes from the ledger (tests/test_lint.py
enforces this with an AST scan for numeric literals).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

from .provenance import Ledger
from .units import ENVELOPE_MATCH_TOL_MM, EXACT_TOL, HALF_TURN_DEG, to_kg_s, to_m3_s, to_mm, to_W


@dataclass
class Part:
    id: str
    name: str
    layer: str                      # structure | plants | water | power | air | crew | work
    lo: list[float]                 # mm
    hi: list[float]                 # mm
    cfd_role: str                   # blockage | source_zone | opening | domain | ignore
    heat_W: float = 0.0
    co2_kg_s: float = 0.0
    h2o_kg_s: float = 0.0
    latent_W: float = 0.0
    opening: dict = field(default_factory=dict)   # for cfd_role == opening: role, face, flow
    ports: list = field(default_factory=list)     # payload ports in the model frame (mm): name, kind, pos, dir, ...
    refs: list[str] = field(default_factory=list)  # ledger paths this part depends on

    @property
    def size(self):
        return [h - l for l, h in zip(self.lo, self.hi)]

    def digest(self) -> str:
        return hashlib.sha256(json.dumps(asdict(self), sort_keys=True).encode()).hexdigest()[:12]


def _fig2_box(L: Ledger, path: str, z0_mm: float, z1_mm: float) -> tuple[list[float], list[float]]:
    """Fig 2 bbox (in, printed frame) + z range (mm) -> model-frame lo/hi in mm."""
    x0, y0, x1, y1 = L.val(path)
    W = L.num("fpm.footprint.width", "in")
    lo = [to_mm(x0, "in"), to_mm(W - y1, "in"), z0_mm]
    hi = [to_mm(x1, "in"), to_mm(W - y0, "in"), z1_mm]
    return lo, hi


def build(L: Ledger | None = None) -> tuple[Ledger, list[Part]]:
    L = L or Ledger()
    parts: list[Part] = []
    Lx = to_mm(L.num("fpm.footprint.length", "in"), "in")
    Ly = to_mm(L.num("fpm.footprint.width", "in"), "in")
    H = (L.val("container.internal")[2] - L.num("container.lining.floor", "mm")
         - L.num("container.lining.ceiling", "mm"))
    attic_lo, attic_hi = _fig2_box(L, "fpm.fig2_zones.attic", 0.0, H)
    parts.append(Part("interior", "FPM interior (steel interior, Fig 2 footprint)", "structure",
                      [0.0, 0.0, 0.0], [Lx, Ly, H], "ignore",
                      refs=["fpm.footprint.length", "fpm.footprint.width", "container.internal"]))
    parts.append(Part("living", "Living volume (CFD domain: interior minus attic)", "air",
                      [0.0, 0.0, 0.0], [attic_lo[0], Ly, H], "domain", refs=["fpm.fig2_zones.attic"]))
    parts.append(Part("attic", "Attic (HVAC compartment, full height)", "air", attic_lo, attic_hi, "ignore",
                      refs=["fpm.fig2_zones.attic", "fpm.attic.is_full_height_compartment"]))

    load = L.num("fpm.electrical.load_average", "W")
    split = L.val("fpm.electrical.heat_split")

    # --- hydroponic NFT wall: canopy volume (source zone) + floor trough (blockage)
    zc0 = to_mm(L.num("fpm.hydroponics.canopy_z_bottom", "m"), "m")
    zc1 = to_mm(L.num("fpm.hydroponics.canopy_z_top", "m"), "m")
    lo, hi = _fig2_box(L, "fpm.fig2_zones.hydroponics", zc0, zc1)
    parts.append(Part("nft_canopy", "NFT tower canopy (27 x 11 sites)", "plants", lo, hi, "source_zone",
                      heat_W=load * split["hydroponics"],
                      refs=["fpm.fig2_zones.hydroponics", "fpm.hydroponics.towers", "fpm.hydroponics.sites_per_tower",
                            "fpm.electrical.heat_split"]))
    # trough sits along the aisle-side (low-y) edge of the hydroponics band
    tlo, thi = _fig2_box(L, "fpm.fig2_zones.hydroponics", 0.0, to_mm(L.num("fpm.hydroponics.trough_height", "in"), "in"))
    trough_depth = to_mm(L.num("fpm.hydroponics.trough_depth", "in"), "in")
    parts.append(Part("nft_trough", "NFT collection trough", "water",
                      [tlo[0], tlo[1], tlo[2]], [thi[0], tlo[1] + trough_depth, thi[2]], "blockage",
                      refs=["fpm.hydroponics.trough_height", "fpm.hydroponics.trough_depth"]))

    # --- Mycoponics enclosure
    lo, hi = _fig2_box(L, "fpm.fig2_zones.mycoponics", 0.0, H * L.num("fpm.mycoponics.enclosure_height_fraction", "-"))
    bay = Part("myco_enclosure", "Mycoponics enclosure (payload bay)", "plants", lo, hi, "blockage",
               refs=["fpm.fig2_zones.mycoponics", "fpm.mycoponics.enclosure_height_fraction"])
    parts.append(bay)

    # --- biomanufacturing payloads in the bay: PUBLIC ENVELOPES ONLY (ledger/payloads.yaml)
    order = L.val("payloads.layout.order")
    clear = L.num("payloads.layout.frame_clearance", "mm")
    sizes = [L.val(f"payloads.{k}.envelope") for k in order]
    inner_x = (bay.hi[0] - bay.lo[0]) - 2 * clear
    gap = (inner_x - sum(sz[0] for sz in sizes)) / (len(order) + 1)
    if gap < 0:
        raise ValueError(f"payloads do not fit in the bay: need {sum(sz[0] for sz in sizes)} mm, have {inner_x} mm")
    heat = {"bioreactor_rack": L.num("payloads.bioreactor_rack.heat", "W"),
            "photobioreactor": L.num("payloads.photobioreactor.led_power", "W"),
            "incubator": L.num("payloads.incubator.heat", "W"), \"sensor_module\": L.num("payloads.sensor_module.heat", "W")}
    powered = bool(L.val("scenario_m0.payloads_powered"))
    rot = L.val("payloads.layout.rotation_deg")
    co2_tube = L.num("payloads.bioreactor_rack.co2_per_tube", "g/day")
    x = bay.lo[0] + clear + gap
    yc = (bay.lo[1] + bay.hi[1]) / 2
    for k, (sx, sy, sz) in zip(order, sizes):
        if sy > (bay.hi[1] - bay.lo[1]) - 2 * clear or sz > bay.hi[2] - bay.lo[2]:
            raise ValueError(f"payload {k} ({sx} x {sy} x {sz} mm) does not fit the bay cross-section")
        lo_p = [x, yc - sy / 2, bay.lo[2]]
        env_chk = L.val(f"payloads.ports.{k}.envelope_check")
        if any(abs(a - b) > ENVELOPE_MATCH_TOL_MM for a, b in zip(env_chk, (sx, sy, sz))):
            raise ValueError(f"payload {k}: ports were derived for envelope {env_chk}, ledger envelope is {[sx, sy, sz]}")
        r = rot[k]
        if r not in (0, HALF_TURN_DEG):
            raise ValueError(f"payload {k}: only 0/180 deg rotations keep the footprint (got {r})")
        ports = []
        for path, rec in L.records.items():
            if not path.startswith(f"payloads.ports.{k}.") or path.endswith("envelope_check"):
                continue
            q = L.val(path)
            u, v, w = q["pos"]
            du, dv, dw = q["dir"]
            if r == HALF_TURN_DEG:           # turn about the envelope's vertical centre line
                u, v, du, dv = sx - u, sy - v, -du, -dv
            ports.append({**q, "pos": [lo_p[0] + u, lo_p[1] + v, lo_p[2] + w], "dir": [du, dv, dw], "ledger": path})
            if q.get("co2_g_day") is not None and abs(q["co2_g_day"] - co2_tube) > EXACT_TOL:
                raise ValueError(f"{path}: co2 {q['co2_g_day']} != ledger payloads.bioreactor_rack.co2_per_tube {co2_tube}")
            if k == "bioreactor_rack" and abs(q["flow_L_min"] - L.num("payloads.bioreactor_rack.vent_flow", "L/min")) > EXACT_TOL:
                raise ValueError(f"{path}: flow differs from payloads.bioreactor_rack.vent_flow")
        parts.append(Part(f"payload_{k}", L.val(f"payloads.{k}.label") if k == "bioreactor_rack" else f"{k} (envelope)",
                          "payloads", lo_p, [x + sx, yc + sy / 2, bay.lo[2] + sz], "payload", ports=ports,
                          refs=[f"payloads.{k}.envelope", "payloads.layout.order", "payloads.layout.frame_clearance",
                                "payloads.layout.rotation_deg"]))
        x += sx + gap
    if powered:     # payload heat (and vented gas) leave the closed enclosure into the room via the bay's fluid shell
        bay.heat_W += sum(heat.values())
        bay.refs.append("scenario_m0.payloads_powered")
        if L.val("payloads.layout.offgas_route") == "bay":
            n_gas = sum(1 for p in parts if p.id == "payload_bioreactor_rack" for q in p.ports if q["kind"] == "gas_out")
            bay.co2_kg_s += to_kg_s(co2_tube * n_gas, "g/day")
            bay.refs += ["payloads.bioreactor_rack.co2_per_tube", "payloads.layout.offgas_route"]

    # --- bottom-wall row
    lo, hi = _fig2_box(L, "fpm.fig2_zones.battery_cabinet", 0.0, to_mm(L.num("fpm.battery_cabinet.height", "in"), "in"))
    parts.append(Part("battery_cabinet", "Battery cabinet (16 x 12 V, inverter/charge controller)", "power", lo, hi,
                      "blockage", heat_W=load * split["battery_cabinet"],
                      refs=["fpm.fig2_zones.battery_cabinet", "fpm.battery_cabinet.height", "fpm.electrical.batteries"]))
    lo, hi = _fig2_box(L, "fpm.fig2_zones.kratcky_dwc", 0.0, to_mm(L.num("fpm.kratky.floor_tub_height", "in"), "in"))
    parts.append(Part("kratky_tub", "Kratky DWC floor tub", "water", lo, hi, "blockage",
                      refs=["fpm.fig2_zones.kratcky_dwc", "fpm.kratky.floor_tub_height", "fpm.kratky.description"]))
    for k in range(int(L.num("fpm.dutch_buckets.count", "-"))):
        lo, hi = _fig2_box(L, f"fpm.fig2_zones.dutch_buckets[{k}]", 0.0,
                           to_mm(L.num("fpm.dutch_buckets.height", "in"), "in"))
        parts.append(Part(f"dutch_bucket_{k + 1}", f"Dutch bucket {k + 1}", "plants", lo, hi, "blockage",
                          refs=[f"fpm.fig2_zones.dutch_buckets[{k}]", "fpm.dutch_buckets.height"]))
    lo, hi = _fig2_box(L, "fpm.fig2_zones.propagation_station", 0.0, H * L.num("fpm.propagation.height_fraction", "-"))
    parts.append(Part("propagation_rack", "Propagation station (10 levels)", "plants", lo, hi, "blockage",
                      heat_W=load * split["propagation"],
                      refs=["fpm.fig2_zones.propagation_station", "fpm.propagation.levels",
                            "fpm.propagation.height_fraction"]))
    lo, hi = _fig2_box(L, "fpm.fig2_zones.work_space", 0.0, to_mm(L.num("fpm.workbench.top_height", "in"), "in"))
    parts.append(Part("workbench_zone", "Work space (bench and under-bench electronics)", "work", lo, hi,
                      "source_zone", heat_W=load * split["workbench"],
                      refs=["fpm.fig2_zones.work_space", "fpm.workbench.top_height"]))

    # --- crew (BVAD reference crewmember, awake)
    W_in = L.num("fpm.footprint.width", "in")
    aisle_y_fig = (L.val("fpm.fig2_zones.dead_space[0]")[3] + L.val("fpm.fig2_zones.work_space")[1]) / 2
    yc = to_mm(W_in - aisle_y_fig, "in")
    bw, bd = [to_mm(v, "m") for v in L.val("crew.body_box")]
    hz = to_mm(L.num("crew.height", "m"), "m")
    xs = L.val("scenario_m0.crew_x")
    for k in range(int(L.num("scenario_m0.crew_on_duty", "-"))):
        xc = to_mm(xs[k], "in")
        parts.append(Part(f"crew_{k + 1}", f"Crewmember {k + 1} (standing, awake)", "crew",
                          [xc - bw / 2, yc - bd / 2, 0.0], [xc + bw / 2, yc + bd / 2, hz], "source_zone",
                          heat_W=to_W(L.num("crew.awake.sensible_heat", "kJ/h"), "kJ/h"),
                          latent_W=to_W(L.num("crew.awake.latent_heat", "kJ/h"), "kJ/h"),
                          co2_kg_s=to_kg_s(L.num("crew.awake.co2", "g/min"), "g/min"),
                          h2o_kg_s=to_kg_s(L.num("crew.awake.water_vapour", "g/min"), "g/min"),
                          refs=["crew.body_box", "crew.height", "crew.awake.sensible_heat", "crew.awake.co2",
                                "crew.awake.water_vapour", "scenario_m0.crew_x", "scenario_m0.crew_on_duty"]))

    # --- HVAC grilles on the attic partition (face x = attic start)
    for role, key in (("inlet", "supply"), ("outlet", "return")):
        gw, gh = [to_mm(v, "in") for v in L.val(f"scenario_m0.hvac.{key}_grille")]
        zc = to_mm(L.num(f"scenario_m0.hvac.{key}_grille_center_z", "m"), "m")
        x = attic_lo[0]
        parts.append(Part(f"hvac_{key}", f"HVAC {key} grille (attic partition)", "air",
                          [x, Ly / 2 - gw / 2, zc - gh / 2], [x, Ly / 2 + gw / 2, zc + gh / 2], "opening",
                          opening={"role": role, "face": "xmax",
                                   "flow_m3_s": to_m3_s(L.num("scenario_m0.hvac.supply_flow", "cfm"), "cfm"),
                                   "supply_T_C": L.num("scenario_m0.hvac.supply_T", "C")},
                          refs=[f"scenario_m0.hvac.{key}_grille", f"scenario_m0.hvac.{key}_grille_center_z",
                                "scenario_m0.hvac.supply_flow", "scenario_m0.hvac.supply_T"]))
    return L, parts


def by_id(parts: list[Part]) -> dict[str, Part]:
    return {p.id: p for p in parts}
