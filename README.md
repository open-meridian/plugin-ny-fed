# plugin-ny-fed

The Federal Reserve Bank of New York's reference rates for
[Open Meridian](https://open-meridian.com): an Open Meridian plugin that puts
the NY Fed's
[reference rates](https://www.newyorkfed.org/markets/reference-rates) --
SOFR, EFFR, OBFR, TGCR and BGCR, the SOFR 30, 90 and 180-day averages and
the SOFR Index -- into a deployment's lake as rates, each business day's
when the NY Fed publishes it, with its history from 2000. It reads the NY
Fed's markets data API, and holds the `data` role, a data plugin. This is
release 0.2.0. How to set it up and use it is in
[docs/](docs/README.md); how a plugin like it is built is documented at
[open-meridian.dev](https://open-meridian.dev).

It is built on the SDK it pins, `open-meridian==0.33.4`, which declares
contract v28; the lake's rates slice is contract v27's (meridian-design
`spec/a-public-rates-and-filings-data-plugin.md`, "plugin-ny-fed").

## What it records

- **One dataset, `<instance>:nyfed_rates`:** rates, pushed when each day's
  appear and pulled for any past day the lake wants; daily; history from 3
  July 2000; New York's day, ending at midnight; no calendar yet; no venue;
  kept, with the NY Fed's notice.
- **Nine records**, the platform's seeded referential records, each found by
  the NY Fed's code as a symbol at `nyfed`: SOFR, EFFR, OBFR, TGCR and BGCR,
  each a fixing with its percentiles, its volume and the money market's
  convention (actual/360, simple); the SOFR 30, 90 and 180-day averages,
  each an average; the SOFR Index, an index level. Never minted; a record
  not held is reported missing, and its rates wait.
- **Exact.** Every figure is a decimal from the text the API wrote.
- **A revision is the next version** of its row, never in place.
- **A published time only where seen:** the NY Fed states none, so a rate
  has one only when the plugin saw it appear on its day of publication.
- **Every answer kept** as received, from the first day, in the storage the
  deployment grants, and named by each row it was first read into.

Its pages, under Manage alone, are the data role's, the same on every data
plugin, and show how it reaches the NY Fed and what it serves, never a rate:
**Connection** (`read_connection`, "No key needed", "Does not stream", and
its Sources) and **Datasets** (`read_datasets`, with its Lag and Records),
each the same through the deployment's MCP.

## Checking it

    make ci-local                                  # lint, tests, plugin check, image, e2e: the pre-push gate
    make preview SHOTS=<dir>                       # each page in a browser with the kit, at 375, 582 and 1280 px

**The data suite.** `tests/test_suite.py` runs the SDK's suite at contract
v27 on the plugin's own conversion. The rates cases the NY Fed presents pass
(a fixing with its percentiles, a same-day revision, an index level), with
liveness, wants, licences and misses. Every other case is about something
the NY Fed never states -- curves and tenors, prices, trades, quotes, venues,
outcomes, and from contract v28 option chains, filings and quotes' quality
-- and is not presented, with why. Its feed delay is presented (ruling
518): a rate it sees appear is stated published when first read, and its
age at the edge is recorded and reported. `an-exact-price` and `a-want-recorded-against`
are about closes from SDK 0.32.1 (ruling 537): with every other case a
rates-only plugin never presents, they are the SDK's `RATES_NOT_PRESENTED`
(ruling 538).

## The terms, summarised

Not legal advice; read the NY Fed's own words before relying on them.

- **Free to use, store and pass on, with its notice.** The NY Fed's
  [Terms of Use](https://www.newyorkfed.org/privacy/termsofuse) allow
  downloading, storing and redistributing its content, with the notice that
  the rates are subject to them, its disclaimer, and no more restrictive
  terms downstream. So the dataset's default licence is kept, with derived
  use and display, no limit on retention, and not one person's terms; the
  notice is shown on the Datasets page. A deployment's licence on its Data
  sources page confirms or replaces it.
- **DTCC data.** SOFR and BGCR are calculated using data licensed to the NY
  Fed by DTCC Solutions LLC.
- **No endorsement.** This project is not affiliated with the Federal
  Reserve Bank of New York, which does not sanction or endorse it.

## Licence

Apache-2.0 (LICENSE, NOTICE). The NY Fed's answer under
`src/ny_fed/responses/` is its reference rates as received on 2026-10-23.
