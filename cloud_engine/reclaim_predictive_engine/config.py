"""
RECLAIM Predictive Engine—configuration and parameter register.

Every parameter carries a provenance tag, consistent with the simulation-
independent posture documented in the Predictive Engine Technical Note:
values are seeded from the SysML model (RECLAIM_MBSE_v5) and the open
literature, refined by logged cRIO data, and only optionally replaced by
COMSOL-derived coefficients later. Nothing here is on a runtime path that
depends on a coupled multiphysics simulation.

Internal units: SI. Temperatures in KELVIN (radiation term requires absolute
temperature). Convert at the I/O boundary only.

RECLAIM Digital Twin. Author: LJW.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional
import math

from .lifecycle import LifecycleConfig

SIGMA_SB = 5.670374419e-8  # Stefan-Boltzmann, W/m^2/K^4


class Provenance(str, Enum):
    """Where a parameter value comes from. Surfaced in the stream manifest."""
    SYSML = "sysml"            # from RECLAIM_MBSE_v5 model / requirements
    LITERATURE = "literature"  # published material property / correlation
    CAD = "cad"                # derived from Fusion 360 geometry (volumes, areas)
    LOGGED_FIT = "logged_fit"  # identified from logged cRIO data
    COMSOL = "comsol"          # optional later refinement (never runtime-required)
    DERIVED = "derived"        # computed from other tagged parameters


@dataclass(frozen=True)
class Tagged:
    """A scalar value with units and provenance."""
    value: float
    unit: str
    source: Provenance
    note: str = ""

    def __float__(self) -> float:  # so it can be used directly in arithmetic
        return float(self.value)


@dataclass
class EnvironmentBlock:
    """
    The ONLY part of the model that the operating scenario changes.
    Convection scales with gravity (g^1/4) and atmospheric density (~P^1/2);
    the surface case disables convection entirely (radiation-limited cooling).
    """
    name: str
    g: float          # gravitational acceleration, m/s^2
    p_atm: float      # ambient pressure, Pa
    t_amb: float      # ambient / coolant reference temperature, K
    convection: bool  # whether buoyant convection is physically present

    P0 = 101325.0
    G0 = 9.80665

    def h_conv(self, dT: float, c_nc: float = 1.3) -> float:
        """Natural-convection coefficient (W/m^2/K), env-scaled. dT in K."""
        if not self.convection or dT <= 0.0:
            return 0.0
        return (c_nc
                * (self.g / self.G0) ** 0.25
                * (self.p_atm / self.P0) ** 0.5
                * dT ** 0.25)


# Scenario presets ------------------------------------------------------------
EARTH_LAB = EnvironmentBlock("earth_lab", g=9.80665, p_atm=101325.0,
                             t_amb=298.0, convection=True)
# Off-nominal 1: inside a pressurized lunar habitat (Rules Table 5).
LUNAR_HABITAT = EnvironmentBlock("lunar_habitat", g=1.625, p_atm=57200.0,
                                 t_amb=295.0, convection=True)
# Off-nominal 2: planetary surface, outside the habitat (near-vacuum).
LUNAR_SURFACE = EnvironmentBlock("lunar_surface", g=1.625, p_atm=3.0e-10,
                                 t_amb=250.0, convection=False)

ENVIRONMENTS = {e.name: e for e in (EARTH_LAB, LUNAR_HABITAT, LUNAR_SURFACE)}


@dataclass
class PhysicalParams:
    """
    Forward-model parameters. Nominal values are seed values; the estimator
    adapts the feedback strength (beta) online and the calibration campaign
    will replace fitted coefficients with logged-data values.
    """
    # Microwave drive
    p_fwd_max: Tagged = field(default_factory=lambda: Tagged(6000.0, "W", Provenance.SYSML, "MW-PR-001"))
    freq: Tagged = field(default_factory=lambda: Tagged(2.45e9, "Hz", Provenance.SYSML, "MW-FR-001"))

    # Temperature-dependent absorption  eta(T) = eta0 * exp(beta*(T - T_ref))
    eta0: Tagged = field(default_factory=lambda: Tagged(0.50, "-", Provenance.LOGGED_FIT, "coupler-derived seed"))
    beta0: Tagged = field(default_factory=lambda: Tagged(2.0e-3, "1/K", Provenance.LITERATURE, "SiC loss-tangent prior; estimated online"))
    t_ref: Tagged = field(default_factory=lambda: Tagged(300.0, "K", Provenance.DERIVED, ""))
    eta_max: Tagged = field(default_factory=lambda: Tagged(0.98, "-", Provenance.LITERATURE, "physical ceiling"))
    # SiC coupling-onset ("ignition"): cold SiC couples poorly until T_ign, then
    # absorption rises sharply. When enabled, eta(T) uses a sigmoid onset instead
    # of the pure exponential (see plant.eta).
    use_ignition: bool = False
    t_ign: Tagged = field(default_factory=lambda: Tagged(700.0, "K", Provenance.LITERATURE, "SiC coupling-onset temperature"))
    k_ign: Tagged = field(default_factory=lambda: Tagged(0.02, "1/K", Provenance.LITERATURE, "coupling-onset sharpness"))
    eta_floor: Tagged = field(default_factory=lambda: Tagged(0.30, "-", Provenance.LITERATURE, "SiC residual cold coupling (good room-temp susceptor)"))

    # Node heat capacities  C = rho*V*Cp  (V from CAD; props from literature)
    c_bed: Tagged = field(default_factory=lambda: Tagged(1500.0, "J/K", Provenance.CAD, "SiC bed/charge core; refine from Fusion volume"))
    c_wall: Tagged = field(default_factory=lambda: Tagged(4000.0, "J/K", Provenance.CAD, "304L chamber wall; refine from Fusion volume"))

    # Bed-to-wall conductance
    u_bw: Tagged = field(default_factory=lambda: Tagged(6.0, "W/K", Provenance.LOGGED_FIT, "effective contact conductance"))

    # Loss surface
    area_s: Tagged = field(default_factory=lambda: Tagged(0.50, "m^2", Provenance.CAD, "outer chamber surface"))
    emiss_wall: Tagged = field(default_factory=lambda: Tagged(0.35, "-", Provenance.LITERATURE, "304L oxidized"))

    # Runaway threshold (calibration TBR)
    t_limit: Tagged = field(default_factory=lambda: Tagged(1173.0, "K", Provenance.LOGGED_FIT, "surface-temp limit, ~900 C"))
    # Operating set-point (target bed temperature for processing)
    t_operate: Tagged = field(default_factory=lambda: Tagged(900.0, "K", Provenance.SYSML, "processing set-point"))
    # HARD chamber-wall material limit. For the 304L plastics chamber this is the
    # 700 C (973 K) continuous service rating (PL-FR-010)—exceeding it is a
    # loss-of-chamber condition, so the advisor treats it as a hard ceiling.
    # Default is non-binding; set per chamber in chamber_params().
    t_wall_limit: Tagged = field(default_factory=lambda: Tagged(1.0e9, "K", Provenance.DERIVED, "no wall limit unless set per chamber"))
    # Latent heat of fusion (metals path): apparent-Cp widening across the melt
    # band so the charge stalls in temperature while absorbing the latent load.
    use_melt: bool = False
    t_melt: Tagged = field(default_factory=lambda: Tagged(933.0, "K", Provenance.SYSML, "Al melt 660 C"))
    latent_heat: Tagged = field(default_factory=lambda: Tagged(397000.0, "J/kg", Provenance.LITERATURE, "Al latent heat"))
    melt_mass: Tagged = field(default_factory=lambda: Tagged(0.5, "kg", Provenance.SYSML, "charge mass; min batch 500 g (DR-2/MT-PR-001)"))
    melt_band: Tagged = field(default_factory=lambda: Tagged(20.0, "K", Provenance.DERIVED, "apparent-Cp band half-width"))

    # Optional chemical exotherm (secondary; disabled by default)
    use_chemical: bool = False
    delta_h: Tagged = field(default_factory=lambda: Tagged(0.0, "J/kg", Provenance.LITERATURE, "TGA prior"))
    e_a: Tagged = field(default_factory=lambda: Tagged(1.2e5, "J/mol", Provenance.LITERATURE, "TGA prior"))
    k0: Tagged = field(default_factory=lambda: Tagged(1.0e8, "1/s", Provenance.LITERATURE, "TGA prior"))
    reactive_mass: Tagged = field(default_factory=lambda: Tagged(0.0, "kg", Provenance.SYSML, ""))

    # Live mass balance (default OFF; opt-in per chamber via chamber_params).
    # When on, the forward model's bed capacity falls as the charge leaves:
    #   C_b(t) = mf_c_inert + m(t)*mf_cp_charge   (SiC bed/crucible stays as c_inert)
    # Plastics: m(t) decays by first-order Arrhenius (endothermic sink, cooling).
    # Metals:   m(t) drains once molten (T_b > t_melt); modest ~10% drop.
    use_massflow: bool = False
    mf_mode: str = "none"          # "pyrolysis" | "drain" | "none"
    mf_c_inert: float = 200.0      # J/K structural capacity that remains
    mf_cp_charge: float = 0.0      # J/kg/K charge specific heat
    mf_m0: float = 0.0             # kg initial charge mass
    mf_k0: float = 2.0e6           # 1/s pyrolysis pre-exponential
    mf_ea: float = 1.2e5           # J/mol pyrolysis activation energy
    mf_dh: float = 1.0e6           # J/kg pyrolysis endothermic enthalpy (heat sink)
    mf_k_drain: float = 1.0e-4     # kg/s per K superheat (metals drain)


@dataclass
class FilterConfig:
    """UKF tuning. dt is the nominal control/telemetry step."""
    dt: float = 1.0  # s
    # van der Merwe scaled sigma-point parameters
    alpha: float = 1e-3
    beta_ukf: float = 2.0
    kappa: float = 0.0
    # Process noise (diag) for [T_b, T_w, beta]; beta walk enables online ID
    q_diag: tuple = (1.0, 1.0, 1e-8)
    # Measurement noise (diag) for [T_b, T_w] from instrument uncertainty budget
    r_diag: tuple = (4.0, 4.0)  # ~2 K (1-sigma) sensors -> variance 4 K^2
    # Initial covariance (diag) for [T_b, T_w, beta]
    p0_diag: tuple = (25.0, 25.0, 1e-6)
    # adaptive process noise (covariance matching) for long, drifting runs
    adaptive: bool = True
    q_window: int = 40


@dataclass
class ForecastConfig:
    horizon: float = 240.0   # s, look-ahead
    dt: float = 2.0          # s, integration step for forecast
    every: int = 1           # run forecast every N estimator steps


@dataclass
class EngineConfig:
    physical: PhysicalParams = field(default_factory=PhysicalParams)
    filt: FilterConfig = field(default_factory=FilterConfig)
    forecast: ForecastConfig = field(default_factory=ForecastConfig)
    lifecycle: LifecycleConfig = field(default_factory=LifecycleConfig)
    environment: str = "earth_lab"
    chamber_id: str = "PL"  # PL (plastics) or MT (metals); selects model order context

    def env(self) -> EnvironmentBlock:
        return ENVIRONMENTS[self.environment]


def parameter_register(p: PhysicalParams) -> list[dict]:
    """Flat, serializable parameter list (symbol, value, unit, source) for audit."""
    rows = []
    for name, v in asdict(p).items():
        if isinstance(v, dict) and "value" in v:  # a Tagged became a dict
            rows.append({"symbol": name, **v})
    return rows


def biot_number(h: float, l_c: float, k_eff: float) -> float:
    """Bi = h*L_c/k_eff. <0.1 -> 1 node; 0.1-1 -> 2-3 node; >>1 -> 1D FV."""
    return h * l_c / k_eff


def recommend_node_count(bi: float) -> int:
    if bi < 0.1:
        return 1
    if bi <= 1.0:
        return 2
    return 3  # signals: prefer 1D finite-volume above this


# --- material properties (the reactor / charge materials) -------------------
# rho [kg/m^3], cp [J/kg/K], k [W/m/K], emiss [-]
MATERIALS = {
    "SiC":          {"rho": 3210, "cp": 750, "k": 120.0, "emiss": 0.85},
    "304L":         {"rho": 8000, "cp": 500, "k": 16.0,  "emiss": 0.35},
    "ZSM5_SiC_bed": {"rho": 1800, "cp": 900, "k": 2.5,   "emiss": 0.85},  # packed-bed effective
    "Al":           {"rho": 2700, "cp": 900, "k": 205.0, "emiss": 0.10},
}


def node_capacity(volume_m3: float, material: str) -> float:
    """Heat capacity C = rho*V*Cp of a node, from CAD volume + material."""
    m = MATERIALS[material]
    return m["rho"] * volume_m3 * m["cp"]


@dataclass
class ChamberGeometry:
    """As-built geometry per reactor; feeds C, A_s, Biot, and node count."""
    name: str
    bed_volume_m3: float
    wall_volume_m3: float
    surface_area_m2: float       # CAD lateral (cylindrical side wall) loss area
    bed_material: str
    wall_material: str
    k_eff_bed: float            # effective bed conductivity (W/m/K)
    diameter_m: float = 0.0      # cylinder OD; enables end-cap loss-area closure
    include_end_caps: bool = True  # QA F5: count the two end caps in the loss area

    def end_cap_area(self) -> float:
        """Area of the two circular end caps (W/m^2 loss surface). The CAD-exported
        `surface_area_m2` is the lateral wall only; a real cylinder also loses heat
        through its end caps (QA finding F5). With d>0 this adds 2*pi*(d/2)^2."""
        if self.diameter_m <= 0.0:
            return 0.0
        return 2.0 * math.pi * (self.diameter_m / 2.0) ** 2

    def total_loss_area(self) -> float:
        return self.surface_area_m2 + (self.end_cap_area() if self.include_end_caps else 0.0)

    def derive(self, h_conv: float = 8.0) -> dict:
        c_bed = node_capacity(self.bed_volume_m3, self.bed_material)
        c_wall = node_capacity(self.wall_volume_m3, self.wall_material)
        # characteristic length = equivalent-sphere radius of the bed (the body
        # whose internal gradient the Biot number judges), not V/A_outer.
        l_c = (3.0 * self.bed_volume_m3 / (4.0 * math.pi)) ** (1.0 / 3.0)
        bi = biot_number(h_conv, l_c, self.k_eff_bed)
        return {"c_bed": c_bed, "c_wall": c_wall, "area_s": self.total_loss_area(),
                "L_c": l_c, "biot": bi, "node_count": recommend_node_count(bi),
                "emiss_wall": MATERIALS[self.wall_material]["emiss"]}


# Geometry MEASURED from CAD STEP files (Pyrolsysis_Chamber.stp, SMELT_Chamber.stp):
#   - surface_area_m2 and wall_volume_m3 are CAD-measured (outer shell / wall solid).
#   - bed_volume_m3 is a cavity-informed ESTIMATE pending the bed/crucible STEP.
# Pyrolysis: outer 11,531 cm^3, inner cavity 10,822 cm^3 -> wall 709 cm^3 (3.2 mm
#   304L), outer surface 0.227 m^2, 203 mm dia x 356 mm.
# SMELT: cavity 20,142 cm^3, outer surface 0.263 m^2, 311 mm dia x 273 mm; modeled
#   as a thin shell, so SiC wall taken at an assumed 6 mm thickness (TBR from CAD).
PLASTICS_GEOMETRY = ChamberGeometry(
    "PL_pyrolysis", bed_volume_m3=2.7e-3, wall_volume_m3=7.10e-4,
    surface_area_m2=0.227, bed_material="ZSM5_SiC_bed", wall_material="304L", k_eff_bed=2.5,
    diameter_m=0.203)  # 203 mm OD -> end caps +0.065 m^2 (F5)
METALS_GEOMETRY = ChamberGeometry(
    "MT_smelt", bed_volume_m3=2.0e-3, wall_volume_m3=1.58e-3,
    surface_area_m2=0.263, bed_material="SiC", wall_material="SiC", k_eff_bed=120.0,
    diameter_m=0.311)  # 311 mm OD -> end caps +0.152 m^2 (F5)


def chamber_params(chamber_id: str = "PL") -> PhysicalParams:
    """Per-chamber parameter set. The two reactors differ in material (304L
    vacuum chamber vs SiC-susceptor) and geometry, so they carry distinct
    coefficients rather than one shared set."""
    from dataclasses import replace
    p = PhysicalParams()
    geom = PLASTICS_GEOMETRY if chamber_id == "PL" else METALS_GEOMETRY
    d = geom.derive()
    p.c_bed = replace(p.c_bed, value=d["c_bed"], source=Provenance.CAD, note=f"{geom.name} bed")
    p.c_wall = replace(p.c_wall, value=d["c_wall"], source=Provenance.CAD, note=f"{geom.name} wall")
    p.area_s = replace(p.area_s, value=d["area_s"], source=Provenance.CAD, note=geom.name)
    p.emiss_wall = replace(p.emiss_wall, value=d["emiss_wall"], source=Provenance.LITERATURE,
                           note=f"{geom.wall_material}")
    c_bed_val = float(p.c_bed)
    if chamber_id == "PL":
        # The 304L *wall* must never exceed 700 C (973 K) continuous service
        # (PL-FR-010)—a HARD ceiling enforced on the wall node T_w. The SiC bed
        # (T_b) tolerates far more, so the bed runaway threshold stays separate.
        p.t_wall_limit = replace(p.t_wall_limit, value=973.0, source=Provenance.SYSML,
                                 note="304L 700 C continuous service HARD limit (PL-FR-010)")
        # Live mass balance: the plastic charge pyrolyzes to gas and leaves, so the
        # bed capacity collapses over the batch. c_inert = ZSM-5/SiC bed that stays.
        p.use_massflow = True
        p.mf_mode = "pyrolysis"
        p.mf_m0 = 1.0                               # kg PE charge (target batch)
        p.mf_cp_charge = 2000.0                     # J/kg/K polyethylene
        p.mf_c_inert = max(200.0, c_bed_val - p.mf_m0 * p.mf_cp_charge)
    if chamber_id == "MT":
        p.use_ignition = True                       # SiC susceptor: coupling onset
        p.use_melt = True                           # aluminium phase change
        p.t_limit = replace(p.t_limit, value=1273.0, note="SiC chamber surface limit")
        # metals processing target must exceed the Al melt point (933 K) with
        # pour superheat; the generic 900 K set-point is a plastics value.
        p.t_operate = replace(p.t_operate, value=1000.0, source=Provenance.SYSML,
                              note="Al pour superheat, >melt 933 K (MT-FR-001/MT-FR-009)")
        # Live mass balance: molten Al drip-casts out after melt; SiC crucible stays.
        p.use_massflow = True
        p.mf_mode = "drain"
        p.mf_m0 = 0.5                               # kg Al charge (min batch)
        p.mf_cp_charge = 900.0                      # J/kg/K aluminium
        p.mf_c_inert = max(200.0, c_bed_val - p.mf_m0 * p.mf_cp_charge)
    return p
