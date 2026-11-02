# Changelog

## 0.3.0

On open-meridian 0.35.1, contract v29 (rulings 1001 to 1005 and 1009 to 1023:
each role one class), on core v29's harness.

- **Each role one class:** `Feed` is the data role's class
  (`meridian.roles.data.Role`), its acts made on itself, and the SDK's
  `Wants`, `rates.Feed` (through its resolve-noting `_Asking`) and `Latency`
  given it (ruling 1023). `__main__`'s `Lake` registers it with
  `meridian.run`, which delivers the settings to `on_settings` before
  anything is heard, hands it the lake's wants, serves the pages and sets
  the figures; its scheduled read, the backfill, tending, the licences' read
  and the feed delay's report are its `run`, started again after a backoff
  should it fail. The hand-wired tasks and signal handling are gone.
- **The settings are declared untyped** (`DECLARED.declared()`), so the
  storage kind's window settings reach `on_settings` beside them, which
  0.35.1's typed delivery leaves out; to be dropped with SDK 0.35.2.
- **Tests and preview:** the role class bound to the suite's `Recorder`
  (`recorder.bind`), what it hears handed by `recorder.hear`.
- **e2e:** the reader a role class run with `meridian.run_async`.
- **The pins:** open-meridian 0.35.1 and plugin-python:0.35.1 by tag and
  digest (`meridian plugin migrate --to 0.35.1`); core v29's runtime and
  harness at `1ae36f0` (chart 0.1.339) by digest; `meridian` 0.1.56 in
  check.yaml (was 0.1.52).

## 0.2.1

SDK 0.33.4: raw-record writes and enum conversion fixes (ruling 937).

- **The pins:** open-meridian 0.33.1 to 0.33.4, and plugin-python:0.33.4 by
  tag and digest (`meridian plugin migrate --to 0.33.4`: only the pins move),
  and the pin README.md states beside them.

## 0.2.0

On open-meridian 0.33.1, contract v28 (plugin-common-v28), on core v28's
harness.

- **The feed delay, reported** (ruling 518, required again from contract
  v28): each rate recorded unasked or for a standing want has its age at
  the edge recorded (`roles.Latency` on the SDK's `Wants`), reported every
  10 seconds (`ReportLatency`). A rate has an age only where the plugin
  states its published time (one seen to appear); `reports-its-feed-delay`
  is presented on a same-day revision.
- **The suite's v28 cases:** option chains, filings and the quality of
  quotes not presented, the SDK's `RATES_NOT_PRESENTED`.
- **`meridian plugin migrate`** (to_0_33_0, to_0_33_1): e2e/reader.py's
  SubjectRefs are `meridian.SubjectRef` (ruling 599).
- **The pins:** open-meridian 0.33.1 and plugin-python:0.33.1 by tag and
  digest; core v28's runtime and harness at `8def82a` (chart 0.1.313) by
  digest; `meridian` 0.1.52 in check.yaml (was 0.1.51).
- The README's "not released yet" is gone.

## 0.1.0

The first version, on open-meridian 0.32.2 (contract v27, the lake's rates
slice).

- **The NY Fed's reference rates as rates**, one dataset (`nyfed_rates`):
  SOFR, EFFR, OBFR, TGCR and BGCR, each a daily fixing with its percentiles
  and volume; the SOFR 30, 90 and 180-day averages; and the SOFR Index, an
  index level. Recorded through the SDK's rates helpers, each about the
  platform's seeded referential record, found by the NY Fed's code as a
  symbol at `nyfed`.
- **Each day's rates pushed** when they appear, read every five minutes in
  the publication windows and hourly otherwise; any past day pulled on a
  want.
- **A revision is the next version** of its row, never in place, published
  later than the rate it revises.
- **A published time only where seen**: when the plugin saw a rate appear
  on its day of publication.
- **The history backfilled** on the first run, a year at a time, back to 3
  July 2000, once.
- **Raw answers kept from the first day**, in the storage the deployment
  grants.
- **The data role's pages**, Connection (with Sources) and Datasets (with
  Lag and Records, under the NY Fed's notice and disclaimer), each a read
  tool on the deployment's MCP.
- **The data suite at v27**: the rates cases the NY Fed presents, and
  liveness; what a rates-only plugin never presents (the SDK's
  `RATES_NOT_PRESENTED`), the curves' cases and the calendar not presented,
  with why.
