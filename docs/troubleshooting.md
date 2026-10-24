# Troubleshooting

## Connection

| What you see | What it means | What to do |
|---|---|---|
| **Not answering** | No check has reached the NY Fed's API: no network, a proxy, or the API down | Check the deployment's outbound access to markets.newyorkfed.org; the plugin tries again within the hour |
| **Answering**, with a warning | An earlier check worked; the last did not | Nothing, usually: the next check runs within the hour. The detail says what failed |
| A notice, **History:** | The backfill stopped: the API did not answer, or it waits for a record not held | It goes on where it stopped within the hour, or a day after the record is held |

## Records

| What you see | What it means | What to do |
|---|---|---|
| **N records not held** | A record's symbol at `nyfed` found no record in your deployment, or two | Ask the platform for it, or merge the two, at the Instruments page; the next check records its rates |
| A rate the plugin could not read | The API stated a value that is not a number | It is not recorded; the Datasets page lists it |
| No published time on a rate | The plugin did not see the rate appear: it was read by the backfill, for an older day, or after a pause | Nothing: a published time is stated only when known |

## Wants and licences

| What you see | What it means | What to do |
|---|---|---|
| A day declined, *source silent* | A weekend, a holiday, or a day not published yet | Wait for the next business day's rates, from about 08:00 New York time |
| A day declined, *beyond history* | A day before 3 July 2000, the NY Fed's first | Nothing: no rate exists for it |
| A subject declined, *not covered* | A record other than the nine, or prices rather than rates | Read it from the plugin that publishes it |
| Datasets: **Not licensed yet** | No deployment admin has licensed the dataset | Ask a deployment admin to license it on Data sources; the page says so within a minute |
