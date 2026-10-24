# Pages

Both pages are the data role's, the same on every data plugin, under
**Manage**, for the plugin's admins. Neither shows a rate. Each is also a
read tool on the deployment's MCP, answering what the page shows, under the
same names on every data plugin.

## Connection (`read_connection`)

How the plugin reaches the NY Fed, and how the last check went:

- the head's status: answering, checking, not answering, or records not
  held;
- **Key:** the mode (Live or Sample data), "No key needed", what the NY Fed
  serves;
- **Limits and use:** the limits it keeps (the NY Fed states none; one
  request at a time, at most one every two seconds, every five minutes
  around publication and hourly otherwise), the requests made, the last
  check and error;
- **Stream:** it does not stream; and **Sources**, one row: the rates the
  API states (SOFR, TGCR, BGCR, the SOFR averages and index, EFFR, OBFR),
  the latest effective date read and the next release expected. Its `…`
  opens one line per rate -- its state, last release, next expected and
  about when -- with the history's backfill, the reads that stated nothing
  new and the answers kept.

## Datasets (`read_datasets`)

What the plugin serves:

- **Served:** its one dataset as the deployment's catalogue lists it, with
  the terms it declares and whether a deployment admin has licensed it,
  what it recorded and declined, and its **Lag**: the median time from the
  start of a rate's day to its publication, for rates seen appear;
- **Wants:** the standing wants it keeps current, and the last wants it
  answered; **Subjects**;
- **Records:** the nine records, one line each: the NY Fed's code, what
  each day's row is, the latest effective date read, and the deployment's
  instrument for it, or why there is none; under the NY Fed's notice and
  disclaimer, and how many revisions were recorded as next versions.
