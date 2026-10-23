# Changelog

## 0.1.0

The first version, on open-meridian 0.32.1 (contract v27, the lake's rates
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
