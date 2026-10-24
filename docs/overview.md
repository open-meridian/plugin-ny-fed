# Overview

The Federal Reserve Bank of New York administers and publishes the US dollar
overnight reference rates every business day. This plugin reads them from
the NY Fed's markets data API and puts them into your deployment's lake as
rates, where your reporting, portfolio and analytics plugins read them.

It is a data plugin: its first-use path, its two pages and its Summary figures are every data plugin's, described once on [Using a data plugin](https://open-meridian.dev/how-to/using-a-data-plugin/). These sections cover what is the NY Fed's own.

## What it records

One dataset, `nyfed_rates`, about nine records the platform keeps for every
deployment:

| Record | Each day's row |
|---|---|
| SOFR, the Secured Overnight Financing Rate | a fixing, with its 1st, 25th, 75th and 99th percentiles and its volume |
| EFFR, the Effective Federal Funds Rate | a fixing, with its percentiles and volume |
| OBFR, the Overnight Bank Funding Rate | a fixing, with its percentiles and volume |
| TGCR, the Tri-Party General Collateral Rate | a fixing, with its percentiles and volume |
| BGCR, the Broad General Collateral Rate | a fixing, with its percentiles and volume |
| The SOFR 30, 90 and 180-day averages | an average, each its own record |
| The SOFR Index | an index level, based at 1.00000000 on 2 April 2018, with the convention of the SOFR it compounds |

A rate is recorded as the NY Fed states it: **3.90** is 3.90 per cent, an
annualised rate on an actual/360 basis, simple. A volume stated in billions
of dollars is recorded as the dollars it is. EFFR before 2016 has no
percentiles or volume, and none is recorded for it.

## When rates arrive

The NY Fed publishes SOFR, TGCR and BGCR at about 08:00 New York time on the
business day after the rate's day, the SOFR averages and index shortly
after, and EFFR and OBFR at about 09:00. The plugin reads every five minutes
around those times and hourly otherwise.

A rate belongs to its effective date, New York's day. The NY Fed states no
publication time, so the plugin records one only when it saw the rate
appear: when its previous read, minutes before on the day of publication,
did not hold it. A rate read later, by the history's backfill or for an
older day, has no published time rather than a wrong one.

## Revisions

The NY Fed revises a published rate on occasion: by about 14:30 New York
time the same day, when it is out by more than one basis point. A revision
is recorded as the rate's **next version**, never in place: the first value
stays in the lake's history, and the revision is published later than it.

## History

On its first run the plugin reads every rate the NY Fed publishes, a year at
a time, from today back to EFFR's first day, 3 July 2000 (SOFR, TGCR and BGCR
from 2 April 2018, OBFR from 1 March 2016, the SOFR averages and index from 2
March 2020), and records it once. Asked for an older day later, it reads it
from the API. Asked for a weekend or a day not published yet, it says the
source has not stated it.

## What it does not do

- It shows no rate on its own pages: rates are read by the plugins that use
  them.
- It never fills a weekend or holiday with a number, and never computes an
  average or index the NY Fed did not publish.
- It records neither the FOMC's target range, which the Federal Reserve
  Board publishes, nor a curve.
