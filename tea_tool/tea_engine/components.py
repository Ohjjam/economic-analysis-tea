"""Chemical component database - molar mass, BP, Cp, ΔHvap, density, prices.

Each component carries one **active** price *and* an optional list of
`price_sources` (multiple curated references). The HTML viewer / Streamlit
UI lets the user pick a source; the TEA recomputes with the chosen value.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class PriceSource:
    """One curated price point with full provenance."""
    value_usd_per_kg: float
    source: str                  # e.g. "Echemi", "ICIS", "Sigma", "Bagemihl 2023"
    year: Optional[int] = None
    region: Optional[str] = None  # e.g. "global", "China spot", "EU contract"
    url: Optional[str] = None
    note: Optional[str] = None

    def label(self) -> str:
        bits = [self.source]
        if self.year:
            bits.append(str(self.year))
        if self.region and self.region != "global":
            bits.append(self.region)
        return " ".join(bits)


@dataclass
class Component:
    name: str
    mw: float                       # g/mol
    bp_C: Optional[float] = None    # °C
    density: Optional[float] = None # g/mL @25°C
    cp: Optional[float] = None      # J/g·°C
    hvap: Optional[float] = None    # J/g
    price_low: Optional[float] = None   # $/kg
    price_high: Optional[float] = None  # $/kg
    price_ref: Optional[str] = None
    role: str = "neutral"           # input | output | utility | solvent | catalyst
    # Multi-source price provenance (new). When `active_source_index` is set,
    # `price_low` is overridden by `price_sources[active_source_index].value`.
    price_sources: List[PriceSource] = field(default_factory=list)
    active_source_index: int = 0    # which entry in price_sources is "live"

    @property
    def price(self) -> float:
        if self.price_sources:
            idx = max(0, min(self.active_source_index, len(self.price_sources) - 1))
            return self.price_sources[idx].value_usd_per_kg
        return self.price_low if self.price_low is not None else 0.0

    def add_source(self, src: PriceSource, make_active: bool = False) -> None:
        self.price_sources.append(src)
        if make_active:
            self.active_source_index = len(self.price_sources) - 1
            self.price_low = src.value_usd_per_kg

    def set_active_source(self, source_label: str) -> bool:
        """Activate a source by its `.label()`. Returns True if matched."""
        for i, s in enumerate(self.price_sources):
            if s.label() == source_label:
                self.active_source_index = i
                self.price_low = s.value_usd_per_kg
                return True
        return False


@dataclass
class ComponentDB:
    components: Dict[str, Component] = field(default_factory=dict)

    def add(self, c: Component) -> None:
        self.components[c.name] = c

    def get(self, name: str) -> Component:
        if name not in self.components:
            raise KeyError(f"Unknown component {name!r}")
        return self.components[name]

    def __contains__(self, name: str) -> bool:
        return name in self.components

    @classmethod
    def default(cls) -> "ComponentDB":
        """Default DB seeded with components used in the reference PET TEA paper."""
        db = cls()
        db.add(Component("PET",   192.17, None, 1.38, 1.13, None, 0.10, 0.40, "Recycling Market 2024 (waste PET)", role="input"))
        db.add(Component("PMA",   1825.25, None, 1.83, None, None, 0.01, None, "Made-in-China", role="catalyst"))
        db.add(Component("H2SO4", 98.08,  337,  1.84, 1.34, 570.96, 0.037, None, "Made-in-China", role="solvent"))
        db.add(Component("DMSO",  78.13,  189,  1.10, 1.91, 677.08, 1.5,  None, "Echemi", role="solvent"))
        db.add(Component("H2O",   18.016, 100,  1.0,  4.18, 2256.45, 0.00022, None, "Nat Commun 2021", role="utility"))
        db.add(Component("TPA",   166.13, None, 1.52, None, None, 0.94, None, "ICIS 2024", role="output"))
        db.add(Component("FA",    46.03,  100.8, 1.22, 2.15, 1005.9, 0.84, None, "ICIS 2024", role="output"))
        db.add(Component("H2",    2.016,  -252.9, 0.0899e-3, 14.3, 446.0, 8.0, None, "Hydrogen Council 2024", role="output"))
        # extras for other process templates
        db.add(Component("CO2",   44.01,  -78.5, 1.98e-3, 0.844, 574.0, 0.05, None, "industrial", role="input"))
        db.add(Component("CO",    28.01,  -191.5, 1.25e-3, 1.04, 215.0, 0.6, None, "industrial", role="output"))
        db.add(Component("HCOOH", 46.03,  100.8, 1.22, 2.15, 1005.9, 0.84, None, "industrial", role="output"))
        db.add(Component("C2H4",  28.05,  -103.7, None, 2.27, 482.0, 1.1, None, "industrial", role="output"))
        db.add(Component("Glucose", 180.16, None, 1.54, 1.18, None, 0.40, None, "industrial", role="input"))
        db.add(Component("Ethanol", 46.07, 78.4, 0.789, 2.46, 841.0, 0.55, None, "industrial", role="output"))
        db.add(Component("KOH",   56.11,  1327, 2.04, 1.18, None, 1.0, None, "industrial", role="solvent"))
        db.add(Component("NaOH",  40.00,  1388, 2.13, 1.50, None, 0.5, None, "industrial", role="solvent"))
        db.add(Component("O2",    32.00,  -183, 1.43e-3, 0.918, 213.0, 0.05, None, "industrial", role="output"))
        # Catalyst / consumables that get periodically replaced
        db.add(Component("KHCO3", 100.12, None, None, None, None, 0.55, None, "industrial", role="solvent"))
        db.add(Component("MEA membrane", 1.0, None, None, None, None, 4_000.0, None,
                          "Bagemihl 2023 (MEA assembly proxy)", role="catalyst"))
        db.add(Component("Cu GDE",  1.0, None, None, None, None, 5_000.0, None,
                          "Bagemihl 2023 (Cu gas-diffusion electrode proxy)", role="catalyst"))
        # Lignin oxidation template: feedstock + monomer products + extraction solvent
        db.add(Component("Organosolv Lignin", 1.0, None, 1.30, 1.40, None, 0.40, 0.60,
                          "Technical lignin (organosolv oak), industrial 2024", role="input"))
        db.add(Component("Vanillin",          152.15, 285, 1.06, 1.20, None, 15.0, 25.0,
                          "Echemi 2024 (synthetic vanillin)", role="output"))
        db.add(Component("Vanillic acid",     168.15, 354, 1.36, 1.20, None, 30.0, 60.0,
                          "Echemi/Alibaba 2024", role="output"))
        db.add(Component("Syringaldehyde",    182.17, 192, 1.21, 1.40, None, 60.0, 120.0,
                          "Specialty chemical 2024", role="output"))
        db.add(Component("Syringic acid",     198.17, 372, 1.36, 1.30, None, 80.0, 150.0,
                          "Specialty chemical 2024", role="output"))
        db.add(Component("Chloroform",        119.38, 61.2, 1.49, 0.96, 247.0, 1.50, 3.0,
                          "Made-in-China/Echemi 2024", role="solvent"))
        # COOR-ORR paired-electrolysis components (260506 TEA workbook)
        db.add(Component("H2O2",  34.014, 150.2, 1.45, 2.62, 1517.0, 1.5, None,
                          "Echemi 2025; 100 wt% basis", role="output"))
        db.add(Component("K2CO3", 138.205, None, 2.43, 0.96, None, 0.89, None,
                          "Echemi 2025", role="output"))
        db.add(Component("Air",   28.97, -194.0, 1.225e-3, 1.005, None, 0.0, None,
                          "ambient", role="utility"))
        db.add(Component("LDG gas (CO surrogate)", 28.01, -191.5, 1.145e-3, 1.04, 215.0,
                          0.0, None, "lignin depolymerization off-gas (waste)",
                          role="input"))
        # Bio-based / biomass electro-oxidation components
        db.add(Component("HMF", 126.11, 116.0, 1.29, 1.66, None, 2.50, 5.0,
                          "5-hydroxymethylfurfural, bulk bio-derived (2024)",
                          role="input"))
        db.add(Component("FDCA", 156.09, 419.0, 1.60, 1.49, None, 4.00, 8.0,
                          "2,5-furandicarboxylic acid; Roylance 2022 TEA",
                          role="output"))
        db.add(Component("Glycerol", 92.09, 290.0, 1.26, 2.43, 974.0, 0.10, 0.50,
                          "Crude glycerol (biodiesel waste, 2024)",
                          role="input"))
        db.add(Component("EG", 62.07, 197.3, 1.11, 2.41, 836.0, 0.80, 1.20,
                          "Ethylene glycol, bulk industrial",
                          role="input"))
        db.add(Component("Glucaric acid", 210.14, None, 1.49, 1.30, None, 5.40, 12.0,
                          "Chemical-route market ~$5.40/kg (electrochemical 54% cheaper)",
                          role="output"))
        db.add(Component("Glycolic acid", 76.05, 100.0, 1.49, 1.65, None, 4.0, 8.0,
                          "Specialty chemical 2024",
                          role="output"))
        db.add(Component("NH2OH", 33.03, 58.0, 1.21, None, None, 1.72, 5.40,
                          "Hydroxylamine, market reference (Mosalpuri 2023)",
                          role="output"))
        db.add(Component("NaNO3", 84.99, None, 2.26, 1.09, None, 0.50, None,
                          "Sodium nitrate (or waste NO3- treated as free)",
                          role="input"))
        db.add(Component("Furfural", 96.08, 162.0, 1.16, 1.61, None, 1.50, 2.0,
                          "Furfural, bulk bio-derived",
                          role="input"))
        db.add(Component("FuroicAcid", 112.08, 230.0, 1.35, 1.37, None, 5.0, 10.0,
                          "2-furoic acid, specialty",
                          role="output"))
        # Green extraction solvents
        db.add(Component("2-MeTHF", 86.13, 80.2, 0.854, 1.83, 374.0, 8.0, 12.0,
                          "2-methyltetrahydrofuran, bio-based (Sigma 2024)",
                          role="solvent"))
        db.add(Component("Acetovanillone", 166.17, 287.0, 1.13, 1.54, None, 30.0, 50.0,
                          "Specialty pharma intermediate (Sigma 2024)",
                          role="output"))
        db.add(Component("Nafion 117", 1100.0, None, 2.10, None, None, 180.0, None,
                          "Chemours Nafion 117 membrane (~$180/m²)",
                          role="catalyst"))

        # ---- Multi-source price seeds (Material cost sheet of 260506 TEA xlsx
        #      + Sigma + literature). The active index defaults to 0 = the
        #      most recent industrial price for bulk chemicals.
        for name, sources in {
            "H2O2": [
                PriceSource(0.60, "Echemi", 2025, url="echemi.com"),
                PriceSource(0.44, "Echemi", 2024),
                PriceSource(0.46, "Echemi", 2023),
                PriceSource(1.087, "Nat Commun 2024", 2024,
                            url="https://www.nature.com/articles/s41467-024-50446-2"),
                PriceSource(1.50, "Echemi 100 wt% basis", 2025),
                PriceSource(1200/1000.0, "260506 TEA workbook ref", 2026,
                            note="Industrial $1200/ton 100 wt% basis"),
            ],
            "K2CO3": [
                PriceSource(0.89, "Echemi", 2025),
                PriceSource(0.95, "Echemi", 2024),
                PriceSource(1.18, "Echemi", 2023),
                PriceSource(247.0, "Sigma reagent grade", 2024,
                            url="sigmaaldrich.com",
                            note="Lab-grade reagent, do not use for plant TEA"),
            ],
            "KOH": [
                PriceSource(0.57, "Echemi", 2025),
                PriceSource(0.64, "Echemi", 2024),
                PriceSource(0.81, "Echemi", 2023),
                PriceSource(111.0, "Sigma reagent grade", 2024,
                            note="Lab-grade reagent, do not use for plant TEA"),
            ],
            "CO": [
                PriceSource(5.68, "Echemi", 2025),
                PriceSource(4.73, "Echemi", 2024),
                PriceSource(2.57, "Echemi", 2023),
                PriceSource(0.60, "Na 2019 paper assumption", 2019,
                            note="Paper assumed industrial bulk CO"),
            ],
            "O2": [
                PriceSource(0.032, "260506 TEA workbook", 2026),
                PriceSource(0.092, "Nat Commun 2024 SI", 2024,
                            url="https://www.nature.com/articles/s41467-024-50446-2"),
                PriceSource(0.11, "imarcgroup oxygen report", 2024,
                            url="https://www.imarcgroup.com/oxygen-pricing-report"),
                PriceSource(0.56, "Echemi", 2025),
                PriceSource(1.19, "Echemi", 2024),
                PriceSource(0.79, "Echemi", 2023),
            ],
            "H2": [
                PriceSource(2.00, "Grey H2 baseline", 2024,
                            note="SMR with natural gas $2-3/kg"),
                PriceSource(4.00, "Blue H2 typical", 2024),
                PriceSource(6.00, "Green H2 PEM electrolysis", 2024),
                PriceSource(8.00, "Hydrogen Council 2024 reference", 2024),
            ],
            "CO2": [
                PriceSource(0.03, "Shin 2021", 2021,
                            note="Industrial CO2 single-pass"),
                PriceSource(0.04, "Bagemihl 2023 DAC", 2023),
                PriceSource(0.06, "Na 2019 captured CO2", 2019),
                PriceSource(0.10, "Industrial bulk CO2", 2024),
            ],
            "PMA": [
                PriceSource(0.01, "Made-in-China bulk", 2024,
                            note="Phosphomolybdic acid, technical grade"),
                PriceSource(0.05, "Industrial reagent estimate", 2024),
                PriceSource(2.00, "Sigma reagent grade", 2024,
                            note="Lab-grade"),
            ],
            "H2SO4": [
                PriceSource(0.037, "Made-in-China bulk", 2024),
                PriceSource(0.10, "ICIS contract Europe", 2024),
                PriceSource(0.05, "USGS commodity 2024", 2024),
            ],
            "DMSO": [
                PriceSource(1.50, "Echemi", 2024),
                PriceSource(2.50, "Sigma bulk", 2024),
                PriceSource(1.20, "Made-in-China spot", 2024),
            ],
            "Vanillin": [
                PriceSource(15.0, "Echemi synthetic vanillin", 2024),
                PriceSource(25.0, "Average market vanillin", 2024),
                PriceSource(80.0, "Natural vanillin from lignin (premium)", 2024),
                PriceSource(200.0, "Bourbon vanilla premium", 2024),
            ],
            "Acetovanillone": [
                PriceSource(30.0, "Sigma specialty", 2024),
                PriceSource(50.0, "Pharma-grade intermediate", 2024),
            ],
            "Glucose": [
                PriceSource(0.40, "Industrial corn syrup basis", 2024),
                PriceSource(0.60, "Food-grade glucose", 2024),
                PriceSource(0.30, "Bulk dextrose 2023 contract", 2023),
            ],
            "Glycerol": [
                PriceSource(0.10, "Biodiesel waste crude glycerol", 2024),
                PriceSource(0.50, "USP-grade glycerol", 2024),
                PriceSource(0.30, "Bulk industrial glycerol", 2024),
            ],
            "Chloroform": [
                PriceSource(1.50, "Made-in-China / Echemi", 2024),
                PriceSource(3.00, "ICIS spec grade", 2024),
                PriceSource(120.0, "Sigma reagent grade", 2024),
            ],
            "2-MeTHF": [
                PriceSource(8.00, "Sigma 2024 bulk", 2024,
                            url="sigmaaldrich.com"),
                PriceSource(12.0, "Specialty distributor", 2024),
                PriceSource(5.00, "Future bulk projection", 2026,
                            note="If demand grows from biomass valorization"),
            ],
            "TPA": [
                PriceSource(0.94, "ICIS 2024 virgin TPA", 2024),
                PriceSource(0.92, "Market price virgin TPA", 2024),
                PriceSource(1.20, "Recycled TPA premium", 2024),
            ],
            "FA": [
                PriceSource(0.84, "ICIS 2024 formic acid", 2024),
                PriceSource(0.53, "Echemi spot 2017-2024 low", 2024),
                PriceSource(1.57, "Echemi spot 2017-2024 high", 2024),
            ],
        }.items():
            if name in db:
                db.components[name].price_sources = sources
                db.components[name].active_source_index = 0
                db.components[name].price_low = sources[0].value_usd_per_kg

        return db
