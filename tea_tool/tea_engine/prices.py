"""Price database with paper-cited defaults + per-component web lookup links.

Why no automatic scraping?  The chemical-price feeds users actually trust
(ICIS, S&P Global, IHS Markit) are paywalled.  Public proxies (ECHEMI,
Made-in-China, Alibaba) work but ban headless requests within minutes.  So
the workflow is:

    1.  Defaults come from the YAML file `data/prices.yaml`.
    2.  Each component carries one or more `lookup` URLs that the UI
        renders as ↗ click-through buttons - the user opens the page,
        copies the latest $/kg, and saves it back into the DB.
    3.  Users can also dump the working DB back to YAML so a project
        can ship its own prices.yaml.

`load_prices_into(db)` mutates a `ComponentDB` to add/update prices.
`save_prices_to_yaml(db, path)` writes the current DB to YAML.
"""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import yaml

from .components import Component, ComponentDB

DEFAULT_PRICES_YAML = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                                   "data", "prices.yaml")


@dataclass
class PriceEntry:
    component: str
    price_low: float
    price_high: Optional[float] = None
    role: str = "neutral"
    tier: str = "market"          # paper | market | estimate
    source: str = ""
    lookup: List[str] = field(default_factory=list)


@dataclass
class PriceDB:
    entries: Dict[str, PriceEntry] = field(default_factory=dict)
    meta: Dict[str, Dict] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str = DEFAULT_PRICES_YAML) -> "PriceDB":
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        db = cls()
        for k, v in raw.items():
            if k == "_meta":
                db.meta = v or {}
                continue
            if not isinstance(v, dict):
                continue
            db.entries[k] = PriceEntry(
                component=k,
                price_low=float(v.get("price_low", 0.0)),
                price_high=(float(v["price_high"]) if v.get("price_high") is not None else None),
                role=str(v.get("role", "neutral")),
                tier=str(v.get("tier", "market")),
                source=str(v.get("source", "")),
                lookup=list(v.get("lookup", []) or []),
            )
        return db

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        out = {}
        for name, e in self.entries.items():
            d = {"price_low": e.price_low, "role": e.role,
                 "tier": e.tier, "source": e.source, "lookup": e.lookup}
            if e.price_high is not None:
                d["price_high"] = e.price_high
            out[name] = d
        out["_meta"] = self.meta
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(out, f, sort_keys=False, allow_unicode=True)

    def lookup_urls(self, component: str) -> List[str]:
        e = self.entries.get(component)
        return e.lookup if e else []


def load_prices_into(db: ComponentDB, path: str = DEFAULT_PRICES_YAML) -> PriceDB:
    """Populate / update a ComponentDB from the YAML price file.

    For components already present in the DB, only fields stored in the YAML
    are overwritten - molar mass, BP, Cp, etc., are left alone.  Components
    that don't yet exist get a stub Component (mw=0) so the TEA can still
    compute revenue/feedstock cost.
    """
    pdb = PriceDB.load(path)
    for name, e in pdb.entries.items():
        if name in db:
            c = db.get(name)
            c.price_low = e.price_low
            c.price_high = e.price_high
            c.price_ref = e.source
            if e.role and c.role == "neutral":
                c.role = e.role
        else:
            db.add(Component(name, mw=0.0, price_low=e.price_low,
                             price_high=e.price_high, price_ref=e.source,
                             role=e.role))
    return pdb


def save_prices_to_yaml(db: ComponentDB, pdb: PriceDB,
                        path: str = DEFAULT_PRICES_YAML) -> None:
    """Snapshot the current ComponentDB prices back to YAML.

    Lookup URLs and metadata from the loaded PriceDB are preserved.
    """
    for name, c in db.components.items():
        e = pdb.entries.get(name)
        if e is None:
            pdb.entries[name] = PriceEntry(
                component=name, price_low=c.price_low or 0.0,
                price_high=c.price_high, role=c.role or "neutral",
                tier="market", source=c.price_ref or "", lookup=[],
            )
        else:
            e.price_low = c.price_low or 0.0
            e.price_high = c.price_high
            e.source = c.price_ref or e.source
    pdb.save(path)


# Convenience: public lookup URL builders for components that don't have
# explicit URLs in the YAML.
def build_default_lookups(component: str) -> List[str]:
    return [
        f"https://www.echemi.com/search.html?keyword={component}",
        f"https://www.made-in-china.com/products-search/hot-china-products/{component}.html",
        f"https://www.alibaba.com/trade/search?SearchText={component}",
    ]
