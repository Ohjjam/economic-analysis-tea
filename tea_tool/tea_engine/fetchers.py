"""Public commodity-price fetchers — no API key required.

Sources (all freely accessible at the time of writing):

    1.  World Bank Pink Sheet (xlsx)         — monthly commodity prices,
        comprehensive coverage of energy, grains, fertilizers, metals.
        https://www.worldbank.org/en/research/commodity-markets

    2.  Trading Economics commodity board     — daily snapshot for ~100
        commodities including methanol, polyethylene, polypropylene, PVC,
        styrene, sulphur, urea, DAP, ethanol, propane, naphtha…
        https://tradingeconomics.com/commodities

    3.  EIA Henry Hub natural gas spot        — US wholesale natural gas.
        https://www.eia.gov/dnav/ng/hist/rngwhhdM.htm

    4.  Frankfurter.app (ECB FX rates)        — for CNY → USD conversion.
        https://www.frankfurter.app

ICIS, S&P Global Platts, IHS Markit are *not* used because they're
paywalled, but the free sources above already cover most commodity-grade
chemicals our TEA tool needs.

Each fetcher returns a list of `PriceRecord(component, price_USD_per_kg,
unit_original, source, date_str, source_url)` records.  The Streamlit UI
applies them to the running ComponentDB and the persistent prices.yaml.
"""
from __future__ import annotations

import io
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
DEFAULT_TIMEOUT = 20


@dataclass
class PriceRecord:
    component: str            # canonical component name in our DB
    price_usd_per_kg: float
    unit_original: str        # e.g. "$/bbl", "CNY/T", "$/Gal"
    price_original: float
    source: str               # short tag, e.g. "WorldBank Pink Sheet"
    source_url: str
    date_str: str             # ISO date or "YYYY-MM"
    note: str = ""


# --------------------------------------------------------------- helpers
def _http_get(url: str, timeout: int = DEFAULT_TIMEOUT) -> bytes:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _gal_to_kg(price_per_gal: float, density_kg_per_L: float = 0.789) -> float:
    """Convert $/gallon → $/kg using the supplied density.  Default for ethanol.

    1 US gallon = 3.7854 L.  Mass = 3.7854 × density (kg/L).
    """
    return price_per_gal / (3.7854 * density_kg_per_L)


def _bbl_to_kg(price_per_bbl: float, density_kg_per_bbl: float = 136.0) -> float:
    """1 barrel ≈ 159 L of crude ≈ 136 kg (light crude)."""
    return price_per_bbl / density_kg_per_bbl


def _mmbtu_to_kg_natgas(price_per_mmbtu: float) -> float:
    """1 MMBtu ≈ 21 kg of natural gas (~50 MJ/kg)."""
    return price_per_mmbtu / 21.0


def _lb_to_kg(price_per_lb: float) -> float:
    return price_per_lb / 0.4536


def _ton_to_kg(price_per_t: float) -> float:
    return price_per_t / 1000.0


# --------------------------------------------------------------- FX
_FX_CACHE: Dict[str, float] = {}


def get_fx_to_usd(currency: str) -> float:
    """Return how many USD 1 unit of `currency` is worth, e.g. CNY → 0.137.

    Uses Frankfurter (ECB) → falls back to open.er-api.com.
    Cached per process run.  Returns 1.0 for USD.
    """
    currency = currency.upper()
    if currency == "USD":
        return 1.0
    if currency in _FX_CACHE:
        return _FX_CACHE[currency]
    try:
        d = json.loads(_http_get(
            f"https://api.frankfurter.app/latest?from={currency}&to=USD"))
        rate = float(d["rates"]["USD"])
    except Exception:
        d = json.loads(_http_get(f"https://open.er-api.com/v6/latest/{currency}"))
        rate = float(d["rates"]["USD"])
    _FX_CACHE[currency] = rate
    return rate


# --------------------------------------------------------------- fetcher: World Bank
WORLD_BANK_PINK_URL = (
    "https://thedocs.worldbank.org/en/doc/"
    "18675f1d1639c7a34d463f59263ba0a2-0050012025/related/"
    "CMO-Historical-Data-Monthly.xlsx"
)

# Map Pink Sheet column-name → (component, unit-converter, density-fallback)
PINK_MAP: Dict[str, Tuple[str, str]] = {
    # column substring : (our-component, original-unit)
    "Crude oil, average":         ("CrudeOil",     "$/bbl"),
    "Natural gas, US":            ("NaturalGas",   "$/MMBtu"),
    "Coal, Australian":           ("Coal",         "$/mt"),
    "Soybeans":                   ("Soybeans",     "$/mt"),
    "Maize":                      ("Maize",        "$/mt"),
    "Wheat, US HRW":              ("Wheat",        "$/mt"),
    "Sugar, world":               ("Sugar",        "$/kg"),
    "Rice, Thai 5%":              ("Rice",         "$/mt"),
    "Phosphate rock":             ("PhosphateRock", "$/mt"),
    "DAP":                        ("DAP",          "$/mt"),
    "TSP":                        ("TSP",          "$/mt"),
    "Urea":                       ("Urea",         "$/mt"),
    "Potassium chloride":         ("KCl",          "$/mt"),
    "Aluminum":                   ("Aluminum",     "$/mt"),
    "Copper":                     ("Copper",       "$/mt"),
    "Lead":                       ("Lead",         "$/mt"),
    "Zinc":                       ("Zinc",         "$/mt"),
    "Nickel":                     ("Nickel",       "$/mt"),
    "Tin":                        ("Tin",          "$/mt"),
    "Iron ore":                   ("IronOre",      "$/dmtu"),
    "Cotton, A Index":            ("Cotton",       "$/kg"),
    "Rubber, RSS3":               ("Rubber",       "$/kg"),
}


def fetch_world_bank() -> List[PriceRecord]:
    raw = _http_get(WORLD_BANK_PINK_URL, timeout=60)
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
    ws = wb["Monthly Prices"]

    rows = list(ws.iter_rows(values_only=True))
    header_name = rows[4]    # row 5 (0-indexed 4)
    # find the latest data row (last row whose col A starts with year)
    data_rows = [r for r in rows[6:] if r[0] and re.match(r"^\d{4}M\d{2}$", str(r[0]))]
    if not data_rows:
        return []
    last = data_rows[-1]
    date_str = str(last[0])  # "YYYYMnn"
    iso_date = f"{date_str[:4]}-{date_str[5:7]}"

    out: List[PriceRecord] = []
    for col_idx, col_name in enumerate(header_name):
        if not col_name:
            continue
        col_str = str(col_name)
        # match against PINK_MAP keys (substring)
        for key, (comp, unit) in PINK_MAP.items():
            if key in col_str:
                v = last[col_idx]
                if v is None or v == "…" or v == "...":
                    break
                try:
                    p_orig = float(v)
                except (ValueError, TypeError):
                    break
                # convert to $/kg
                if unit == "$/mt":
                    p_kg = _ton_to_kg(p_orig)
                elif unit == "$/kg":
                    p_kg = p_orig
                elif unit == "$/bbl":
                    p_kg = _bbl_to_kg(p_orig)
                elif unit == "$/MMBtu":
                    p_kg = _mmbtu_to_kg_natgas(p_orig)
                elif unit == "$/dmtu":
                    p_kg = p_orig / 1000.0   # treat dmtu as ~ ton
                else:
                    p_kg = p_orig
                out.append(PriceRecord(
                    component=comp, price_usd_per_kg=p_kg,
                    unit_original=unit, price_original=p_orig,
                    source="World Bank Pink Sheet",
                    source_url=WORLD_BANK_PINK_URL,
                    date_str=iso_date,
                    note=col_str,
                ))
                break
    return out


# --------------------------------------------------------------- fetcher: Trading Economics
TE_URL = "https://tradingeconomics.com/commodities"

# Trading-Economics name → (component, original unit, conversion)
TE_MAP: Dict[str, Tuple[str, str]] = {
    "Methanol":           ("Methanol",   "CNY/T"),
    "Polyethylene":       ("Polyethylene", "CNY/T"),
    "Polypropylene":      ("Polypropylene", "CNY/T"),
    "Polyvinyl":          ("PVC",        "CNY/T"),
    "Styrene":            ("Styrene",    "CNY/T"),
    "Synthetic Rubber":   ("SyntheticRubber", "CNY/T"),
    "Soda Ash":           ("SodaAsh",    "CNY/T"),
    "Sulfur":             ("Sulfur",     "CNY/T"),
    "Phosphorus":         ("Phosphorus", "CNY/T"),
    "Bitumen":            ("Bitumen",    "CNY/T"),
    "Lithium":            ("Lithium",    "CNY/T"),
    "Urea":               ("Urea",       "USD/T"),
    "Di-ammonium":        ("DAP",        "USD/T"),
    "Ethanol":            ("Ethanol",    "USD/Gal"),
    "Naphtha":            ("Naphtha",    "USD/T"),
    "Propane":            ("Propane",    "USD/Gal"),
    "Crude Oil":          ("CrudeOil",   "USD/Bbl"),
    "Brent":              ("BrentCrude", "USD/Bbl"),
    "Natural gas":        ("NaturalGas", "USD/MMBtu"),
    "Coal":               ("Coal",       "USD/T"),
    "Coking Coal":        ("CokingCoal", "USD/T"),
    "Aluminum":           ("Aluminum",   "USD/T"),
    "Copper":             ("Copper",     "USD/Lbs"),
    "Lead":               ("Lead",       "USD/T"),
    "Zinc":               ("Zinc",       "USD/T"),
    "Nickel":             ("Nickel",     "USD/T"),
    "Tin":                ("Tin",        "USD/T"),
    "Iron Ore":           ("IronOre",    "USD/T"),
    "HRC Steel":          ("Steel",      "USD/T"),
}


def fetch_tradingeconomics() -> List[PriceRecord]:
    h = _http_get(TE_URL).decode("utf-8", errors="replace")
    rows = re.findall(r'<tr[^>]*data-symbol="([^"]+)"[^>]*>(.*?)</tr>', h, re.S)
    out: List[PriceRecord] = []
    for sym, body in rows:
        cells = re.findall(r'<td[^>]*>(.*?)</td>', body, re.S)
        if len(cells) < 9:
            continue
        nm = re.search(r'<a[^>]*>(.*?)</a>', cells[0], re.S)
        if not nm:
            continue
        name = re.sub(r'<[^>]+>', '', nm.group(1)).strip()
        if name not in TE_MAP:
            continue
        comp, unit = TE_MAP[name]

        price_txt = re.sub(r'<[^>]+>', '', cells[1]).strip().replace(",", "")
        try:
            p_orig = float(price_txt)
        except ValueError:
            continue
        date = re.sub(r'<[^>]+>', '', cells[8]).strip()

        # Convert to USD/kg
        if unit == "CNY/T":
            usd_per_t = p_orig * get_fx_to_usd("CNY")
            p_kg = _ton_to_kg(usd_per_t)
        elif unit == "USD/T":
            p_kg = _ton_to_kg(p_orig)
        elif unit == "USD/Bbl":
            p_kg = _bbl_to_kg(p_orig)
        elif unit == "USD/MMBtu":
            p_kg = _mmbtu_to_kg_natgas(p_orig)
        elif unit == "USD/Gal":
            # ethanol density 0.789, propane 0.493
            density = 0.493 if comp == "Propane" else 0.789
            p_kg = _gal_to_kg(p_orig, density)
        elif unit == "USD/Lbs":
            p_kg = _lb_to_kg(p_orig)
        else:
            p_kg = p_orig

        out.append(PriceRecord(
            component=comp, price_usd_per_kg=p_kg,
            unit_original=unit, price_original=p_orig,
            source="Trading Economics",
            source_url=f"{TE_URL} ({sym})",
            date_str=date,
            note=name,
        ))
    return out


# --------------------------------------------------------------- aggregator
def fetch_all() -> Tuple[List[PriceRecord], Dict[str, str]]:
    """Run every fetcher; return (records, status-by-source).

    Status is a dict like {"Trading Economics": "✓ 28 records",
                           "World Bank Pink Sheet": "✓ 22 records",
                           "Frankfurter FX": "✓ 1 USD = 6.83 CNY"}.
    """
    status: Dict[str, str] = {}
    records: List[PriceRecord] = []

    for name, fn in [("World Bank Pink Sheet", fetch_world_bank),
                     ("Trading Economics",      fetch_tradingeconomics)]:
        try:
            recs = fn()
            records.extend(recs)
            status[name] = f"OK — {len(recs)} records"
        except Exception as e:
            status[name] = f"FAIL — {type(e).__name__}: {str(e)[:60]}"

    if "CNY" in _FX_CACHE:
        status["Frankfurter FX (CNY→USD)"] = f"OK — 1 CNY = {_FX_CACHE['CNY']:.4f} USD"
    return records, status


def apply_records_to_db(records: List[PriceRecord], db, pdb,
                        respect_paper_tier: bool = True) -> Dict[str, str]:
    """Mutate ComponentDB and PriceDB in place.

    By default we do NOT overwrite components whose price_db tier is "paper"
    — those are the authoritative numbers from the TEA paper template.  Pass
    respect_paper_tier=False to override.

    Returns a per-component log of what changed.
    """
    log: Dict[str, str] = {}
    for r in records:
        # Find target component name (case-insensitive, and try a couple of aliases)
        canonical = None
        for cand in (r.component, r.component.upper(), r.component.lower(),
                     r.component.replace("Crude", "CrudeOil")):
            if cand in db.components:
                canonical = cand; break
            if cand in pdb.entries:
                canonical = cand; break
        if canonical is None:
            # Add a stub if it's not in the DB at all
            from .components import Component
            db.add(Component(r.component, mw=0.0,
                             price_low=r.price_usd_per_kg,
                             price_ref=f"{r.source} {r.date_str}",
                             role="neutral"))
            from .prices import PriceEntry
            pdb.entries[r.component] = PriceEntry(
                component=r.component, price_low=r.price_usd_per_kg,
                role="neutral", tier="market",
                source=f"{r.source} ({r.note}) {r.date_str}",
                lookup=[r.source_url],
            )
            log[r.component] = f"added @ ${r.price_usd_per_kg:.4f}/kg"
            continue
        # Tier-paper protection
        existing = pdb.entries.get(canonical)
        if existing and existing.tier == "paper" and respect_paper_tier:
            log[canonical] = f"skipped (tier=paper, locked)"
            continue
        # Update both DB and PriceDB
        if canonical in db.components:
            db.components[canonical].price_low = r.price_usd_per_kg
            db.components[canonical].price_ref = f"{r.source} {r.date_str}"
        if existing is not None:
            existing.price_low = r.price_usd_per_kg
            existing.source = f"{r.source} ({r.note}) {r.date_str}"
            existing.tier = "market"
            if r.source_url and r.source_url not in existing.lookup:
                existing.lookup.insert(0, r.source_url)
        log[canonical] = (f"${r.price_usd_per_kg:.4f}/kg  "
                          f"({r.price_original} {r.unit_original}, {r.source}, {r.date_str})")
    return log
