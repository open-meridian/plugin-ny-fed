# Setup

## Launching it

The NY Fed's reference rates need no key and no account: the markets data
API is public. Launch the plugin and approve its one role, `data` (a data
plugin). It reads the current rates at once, then backfills the NY Fed's
history, about 27 requests, once.

Its settings, in the dashboard's Settings form:

- **Raw responses window** and **past the window** (the SDK's): how long the
  NY Fed's answers are kept in the plugin's storage, ten years by default,
  and whether they are then archived, kept or deleted.
- **Sample data**, on a deployment installed for development only: the NY
  Fed's rates recorded on 23 October 2026, committed with the plugin, in
  place of the API. For trying it offline.

## Its dataset

On the deployment's **Data sources** page (deployment admins):

1. **License `<instance>:nyfed_rates`.** The catalogue's default is kept,
   with derived use and display, no limit on retention, and not one
   person's terms. The NY Fed asks for its notice and disclaimer with the
   rates (see Terms); record that in your licence's note. Confirm the
   default, or set your own, with a note saying why.
2. **Entitle** each plugin that reads rates: your reporting, portfolio or
   signal plugin, and the analytics component.
3. **Priority**, where another dataset also states one of these records,
   such as the Federal Reserve Board's H.15 for EFFR: put the one your
   readers should read first.

## Its records

Each rate is about one of nine records the platform seeds, each found by the
NY Fed's code as a symbol at `nyfed` (SOFR, EFFR, OBFR, TGCR, BGCR, the
three SOFR averages and the SOFR Index). Your deployment pulls each from the
platform the first time the plugin asks. The Datasets tab shows each
record's instrument, or why there is none. A record the deployment does not
hold is reported missing once a day, and its rates wait until it is held;
the others are recorded meanwhile.

## The calendar

The NY Fed publishes on the US government securities market's business
days. No calendar for them is held yet, so the dataset names none and the
plugin expects rates Monday to Friday. On a holiday it reads, finds no rate,
and records nothing.
