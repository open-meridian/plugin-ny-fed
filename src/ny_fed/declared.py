"""What this version declares beside its role, `data` (W8.1, W4.1; the
catalogue from contract v18, its rates from v27), built from code and used
twice: `__main__` registers with it, and `meridian plugin upload` reads it
from the built image (pyproject.toml's `[tool.meridian] declaration`).

**The catalogue: one dataset, `nyfed_rates`** (spec/a-public-rates-and-
filings-data-plugin, "plugin-ny-fed" and §3; its key approved with the
batch, 2026-10-14). The Federal Reserve Bank of New York's reference rates,
each day's pushed when the NY Fed publishes it, any past day pulled when the
lake wants it:

- `vendor` the Federal Reserve Bank of New York; no aggregator, since the
  plugin reads the NY Fed's markets data API itself;
- `data_types` rates alone (contract v27's `Rate`): SOFR, EFFR, OBFR, TGCR
  and BGCR each a daily fixing with its percentiles and volume, the SOFR
  30, 90 and 180-day averages each an average, and the SOFR Index an index
  level (convert.py);
- `modes` `push` (each day's rates recorded when they appear) and `pull` (a
  past day, on a want);
- `cadence` a day, in seconds: the NY Fed publishes each business day;
- `history` about 9,610 days, as the NY Fed publishes them: EFFR from 3
  July 2000, OBFR from 1 March 2016, SOFR, TGCR and BGCR from 2 April 2018,
  the SOFR averages and index from 2 March 2020;
- its day New York's, ending at midnight (`America/New_York`, 0): a rate's
  business date is its effective date, as the NY Fed states it;
- no calendar: the spec's US government securities calendar (Q15, SIFMA's
  bond-market closes) is curated on a miss and none is held yet, so the
  dataset declares none, and the plugin takes Monday to Friday (feed.py);
- no venue: the rates are the NY Fed's, as administrator, no venue's;
- the licence the NY Fed's terms suggest (§7): kept, derived use not
  restricted and display, with no limit on retention, and not one person's
  terms. The NY Fed's notice and disclaimer, the attribution its terms ask
  for (`ATTRIBUTION`), are stated on the Datasets page and in docs/terms.md.
  SDK 0.32.2 writes the licence's attribution fields (redistribution
  allowed with attribution, this notice, copyright with citation required,
  no more restrictive terms), but core a5da59a's upload does not carry them
  yet, so a version declaring them is refused at registration: they are
  declared once core carries them. A deployment's licence confirms or replaces the default on
  the Data sources page; the plugin says nothing of whether a deployment
  meets anyone's terms.

**The subjects** are the platform's seeded referential records (contract
v27, W1.1; the spec's §2), each named by the NY Fed's code as a
source-scoped `symbol` at `nyfed` (`SUBJECTS`): never a FIGI guessed, and
never minted.

**Storage:** the API's answers (raw.py), archivable, ten years by default.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from meridian import DatasetDeclaration, DatasetLicence
from meridian.declaration import RecordKind

from .raw import DEFAULT_WINDOW_DAYS, RESPONSES

#: The dataset's key: its rows name `<instance>:nyfed_rates`.
NYFED_RATES = "nyfed_rates"
VENDOR = "Federal Reserve Bank of New York"
#: A day, in seconds.
CADENCE = 86_400
#: The oldest rate the NY Fed publishes: EFFR's, 3 July 2000.
EARLIEST = date(2000, 7, 3)
#: From EARLIEST, in days, as the catalogue states it (to the end of 2026).
HISTORY = 9_610
#: Each rate's day: New York's, midnight to midnight.
DAY_TIME_ZONE = "America/New_York"
DAY_END_MINUTE = 0
#: Where the symbols the platform seeds are scoped: the administrator's code.
SYMBOL_SOURCE = "nyfed"
RATE = "meridian.v1.Rate"

#: The NY Fed's notice and disclaimer, as its Terms of Use ask them of
#: whoever uses or passes on its reference rates, and its attribution.
ATTRIBUTION = (
    "Source: Federal Reserve Bank of New York. SOFR, EFFR, OBFR, TGCR, BGCR, the SOFR "
    "Averages and the SOFR Index are subject to the Terms of Use posted at newyorkfed.org. "
    "The New York Fed is not responsible for publication of them by this plugin, does not "
    "sanction or endorse it, and has no liability for your use. SOFR and BGCR are "
    "calculated using data licensed to the New York Fed by DTCC Solutions LLC."
)

NYFED_RATES_DATASET = DatasetDeclaration(
    key=NYFED_RATES,
    vendor=VENDOR,
    data_types=[RATE],
    modes=["push", "pull"],
    cadence=CADENCE,
    history=HISTORY,
    licence_default=DatasetLicence(
        kept=True,
        derived_use_terms="not_restricted",
        derived_use=True,
        display=True,
    ),
    day_time_zone=DAY_TIME_ZONE,
    day_end_minute=DAY_END_MINUTE,
)

RESPONSES_KIND = RecordKind(RESPONSES, "Raw responses", window_days=DEFAULT_WINDOW_DAYS)


@dataclass(frozen=True)
class Subject:
    """One referential record the plugin records against: the NY Fed's code
    for it (the seeded symbol), its name, its instrument type, the rate type
    the API states it under and the field holding its value, and what its
    rows are (`fixing`, `average`, `index_level`)."""

    code: str
    name: str
    instrument_type: str
    kind: str
    rate_type: str
    field: str


#: The nine records, in the NY Fed's order: the five reference rates, the
#: three SOFR averages and the SOFR Index.
SUBJECTS: tuple[Subject, ...] = (
    Subject("SOFR", "Secured Overnight Financing Rate", "interest_rate", "fixing",
            "SOFR", "percentRate"),
    Subject("EFFR", "Effective Federal Funds Rate", "interest_rate", "fixing",
            "EFFR", "percentRate"),
    Subject("OBFR", "Overnight Bank Funding Rate", "interest_rate", "fixing",
            "OBFR", "percentRate"),
    Subject("TGCR", "Tri-Party General Collateral Rate", "interest_rate", "fixing",
            "TGCR", "percentRate"),
    Subject("BGCR", "Broad General Collateral Rate", "interest_rate", "fixing",
            "BGCR", "percentRate"),
    Subject("SOFR 30-day average", "30-day Average SOFR", "interest_rate", "average",
            "SOFRAI", "average30day"),
    Subject("SOFR 90-day average", "90-day Average SOFR", "interest_rate", "average",
            "SOFRAI", "average90day"),
    Subject("SOFR 180-day average", "180-day Average SOFR", "interest_rate", "average",
            "SOFRAI", "average180day"),
    Subject("SOFR Index", "SOFR Index", "index", "index_level", "SOFRAI", "index"),
)  # fmt: skip

BY_CODE = {s.code: s for s in SUBJECTS}
