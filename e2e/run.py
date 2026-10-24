"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v27), as instance `ny-fed`, beside `reader`, a reporting plugin
(e2e/reader.py) entitled to its dataset, and the harness's admin. Run from
the repository's root by the Makefile, which builds the image and writes the
harness's plugins first; standard library only.

1. The API unreachable: the plugin's hosts file sends the NY Fed's API
   nowhere, so its first check fails, and Connection says so -- "Not
   answering", the data role's word -- and records nothing.
2. Sample data on (a developer's setting, accepted on the harness): the
   plugin reads the committed answer's last ten days, 13 to 23 October
   2026; each of the nine records resolves by its symbol at `nyfed`, the
   administrator's code with its source, to the platform's `INS-` record;
   the 76 current rates are recorded, then the history backfilled from 3
   August, 517 rates in all; Connection names the days the API stated, and
   Datasets each record's instrument.
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show, under the data role's names,
   and core's `dashboard__list_datasets` lists `ny-fed:nyfed_rates` as the
   catalogue declares it: rates, push and pull, daily, New York's day ending
   at midnight, no calendar, its licence default kept, derived use not
   restricted, display.
4. Licensed and entitled at the Data sources page: the reader is entitled.
5. Read back: SOFR of 22 October is a fixing of 3.90 per cent, act/360
   simple, its four percentiles and USD 2,945,000,000,000 of volume, version
   1, naming its raw record; the SOFR Index of 23 October an index level of
   1.26398658 based at 2 April 2018; the 90-day average of 23 October an
   average of 3.75301.
6. Wanted: a Saturday, 17 October, and a day before the recording, 31 July,
   are asked of the plugin, which declines each `source_silent`.
7. `store lake` is e2e/expected.lake, each record named by its code.
8. A new container: it reads the rates again and records nothing twice, its
   backfill not read again; its licence read on start.
"""

import json
import os
import subprocess
import sys
import time

PROJECT = "ny-fed-e2e"
LOG = ".e2e/runner.log"
COMPONENTS = ".e2e/components.log"
COMPOSE = ["docker", "compose", "-p", PROJECT, "-f", ".e2e/harness/compose.yaml",
           "-f", ".e2e/harness/plugins.yaml", "-f", "e2e/plugin.yaml"]
DATASET = "ny-fed:nyfed_rates"
CODES = ["SOFR", "EFFR", "OBFR", "TGCR", "BGCR", "SOFR 30-day average",
         "SOFR 90-day average", "SOFR 180-day average", "SOFR Index"]
#: Every rate the recording states: 57 fixing days of five rates, 58 of SOFRAI's four.
ALL_RATES = 57 * 5 + 58 * 4
#: The current range's: 13 to 23 October.
CURRENT_RATES = 8 * 5 + 9 * 4
#: When the conductor hands the licence list on again after its start
#: (meridian-core's conductor, FIRST_AGAIN_AFTER, 60 s), and a margin.
LICENCE_LIST_AGAIN_SECONDS = 75


class Failed(Exception):
    pass


def log(text):
    with open(LOG, "a", encoding="utf-8") as kept:
        kept.write(text + "\n")


def compose(*args, check=True, timeout=600):
    done = subprocess.run(COMPOSE + list(args), capture_output=True, text=True,
                          timeout=timeout)
    log(f"$ compose {' '.join(args)[:300]}\n{done.stdout[-4000:]}{done.stderr[-2000:]}")
    if check and done.returncode != 0:
        raise Failed(f"compose {' '.join(args)[:200]}: {(done.stdout + done.stderr).strip()[-600:]}")
    return done


def runner(*args, check=True):
    done = compose("run", "--rm", "-T", "runner", *args, check=check)
    return done.stdout if check else done


def must(condition, why):
    if not condition:
        raise Failed(why)


def until(seconds, attempt, what):
    deadline = time.monotonic() + seconds
    last = None
    while True:
        try:
            answer = attempt()
        except Failed as failed:
            answer, last = None, failed
        if answer:
            return answer
        if time.monotonic() > deadline:
            raise Failed(f"{what}, in {seconds} seconds" + (f": {last}" if last else ""))
        time.sleep(2)


def page(instance, level, path):
    said = runner("page", "--instance", instance, "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{instance} {path} answered {said[-600:]}")
    return body


def rates(subject, day):
    """The reader's read of the plugin's dataset, by business date."""
    return json.loads(page("reader", "read", f"/rates?subject={subject}&date={day}&dataset={DATASET}"))


def call(tool, arguments=None):
    done = runner("mcp", "call", tool, json.dumps(arguments or {}), check=False)
    try:
        answer = json.loads(done.stdout)
    except ValueError:
        raise Failed(f"{tool}: no answer: {(done.stdout + done.stderr)[-400:]}")
    must(answer.get("outcome") in ("read", "unchanged"), f"{tool} answered {done.stdout[-700:]}")
    return answer["data"]


def store_lake():
    return compose("run", "--rm", "-T", "store", "lake").stdout


def named(lines, codes):
    """`store lake` with each record's ID as its code, wherever it appears."""
    out = []
    for line in lines.strip().splitlines():
        for instrument, code in codes.items():
            line = line.replace(instrument, code)
        out.append(line)
    return "\n".join(sorted(out)) + "\n"


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    up = time.monotonic()
    runner("ready")
    runner("ready", "--instance", "reader")

    # 1. The API unreachable.
    said = runner("page", "--level", "admin", "/", "--until", "Not answering", "--seconds", "90")
    must("Error" in said, f"step 1, Connection names why the API was not reached: {said[-500:]}")
    lake = store_lake()
    must("row|" not in lake, f"step 1, nothing recorded with the API unreachable: {lake}")

    # 2. Sample data: the nine records resolved, the rates recorded, the history backfilled.
    # The conductor hands the platform's licence list on at its start and again a
    # minute later, whole; the instrument store, started after the first, sends
    # an administrator's symbol to the platform only once it holds the list
    # (ruling 545). A miss is reported, and not asked again, for the rest of the
    # day (the SDK's rates.Feed.subject), so the run waits that minute out.
    time.sleep(max(0, LICENCE_LIST_AGAIN_SECONDS - (time.monotonic() - up)))
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/", "--until", "6 sources, latest Fri 23 Oct", "--seconds", "120")
    until(180, lambda: store_lake().count(f"row|{DATASET}|rate|") >= ALL_RATES,
          f"step 2, the {ALL_RATES} rates of the recording were not recorded")
    datasets = page("ny-fed", "admin", "/datasets")
    must(datasets.count("<code>INS-") >= len(CODES) and "not found" not in datasets,
         f"step 2, Datasets names each record's instrument: {datasets[-1500:]}")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", "ny-fed:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    answered = call(read_connection)
    sources = {s["source"]: s for s in answered["sources"]}
    must(answered["latest_day"] == "2026-10-23" and answered["first_day"] == "2026-10-13"
         and answered["mode"] == "Sample data" and answered["credentials"] == []
         and answered["sessions"] is None and answered["said"] == "Sample data"
         and sources["SOFR"]["last_release"] == "2026-10-22"
         and sources["SOFR averages and index"]["last_release"] == "2026-10-23"
         and answered["backfill"] == "Done: 2026 to 2026",
         f"step 3, read_connection: {answered}")
    read = call(read_datasets)
    codes = {r["instrument_id"]: r["code"] for r in read["records"] if r["instrument_id"]}
    ids = {code: instrument for instrument, code in codes.items()}
    must([r["code"] for r in read["records"]] == CODES and len(ids) == len(CODES)
         and all(i.startswith("INS-") for i in ids.values())
         and read["served"][0]["dataset"] == DATASET and "newyorkfed.org" in read["attribution"],
         f"step 3, read_datasets names each record's INS- instrument: {read}")
    must(all(instrument in datasets for instrument in codes),
         "step 3, Datasets shows what read_datasets answers")
    # The conductor publishes the launched catalogues on a change and every
    # minute: a harness's instance is launched once its sidecar has reported.
    listed = until(90, lambda: {d["dataset"]: d for d in call("dashboard__list_datasets")["datasets"]
                                if d["dataset"] == DATASET},
                   "step 3, core never listed the dataset")
    entry = listed.get(DATASET, {}).get("catalogue_entry", {})
    terms = entry.get("licence_default", {})
    # The licence's attribution fields wait for core to carry them (the
    # notice is on Datasets): the default as the SDK writes it today.
    must(entry.get("modes") == ["push", "pull"] and entry.get("day_time_zone") == "America/New_York"
         and not entry.get("day_end_minute") and entry.get("cadence") == 86400
         and not entry.get("calendar_id") and entry.get("data_types") == ["meridian.v1.Rate"]
         and terms.get("kept") is True and terms.get("derived_use_terms") == "not_restricted"
         and terms.get("display") is True and terms.get("personal_use") is False,
         f"step 3, core lists the catalogue as declared: {listed.get(DATASET)}")

    # 4. Licensed and entitled.
    runner("licence", DATASET, "kept=true", "retention_days=0", "derived_use=true", "display=true",
           "personal_use=false", "note=The NY Fed's reference rates, with its notice and disclaimer.")
    runner("entitle", "--instance", "reader", DATASET, "note=The e2e's reader reads the rates.")
    runner("grant", "--instance", "reader", "--level", "read")

    # 5. Read back, about the right records.
    sofr = until(60, lambda: rates(ids["SOFR"], "2026-10-22")["rates"],
                 "step 5, SOFR of 22 October was not read")
    must(len(sofr) == 1, f"step 5, one SOFR fixing on 22 October: {sofr}")
    [one] = sofr
    must(one["kind"] == "RATE_KIND_FIXING" and one["value"] == "3.90"
         and one["unit"] == "VALUE_UNIT_PERCENT" and one["day_count"] == "DAY_COUNT_ACT_360"
         and one["compounding"] == "COMPOUNDING_SIMPLE"
         and one["percentiles"] == {"1": "3.83", "25": "3.88", "75": "3.95", "99": "3.98"}
         and one["volume"] == "2945000000000" and one["version"] == 1
         and one["subject"] == ids["SOFR"] and one["raw"].startswith("responses/"),
         f"step 5, SOFR of 22 October as the NY Fed states it: {one}")
    [index] = rates(ids["SOFR Index"], "2026-10-23")["rates"]
    must(index["kind"] == "RATE_KIND_INDEX_LEVEL" and index["value"] == "1.26398658"
         and index["unit"] == "VALUE_UNIT_INDEX" and index["index_base"] == "2018-04-02=1.00000000",
         f"step 5, the SOFR Index of 23 October: {index}")
    [average] = rates(ids["SOFR 90-day average"], "2026-10-23")["rates"]
    must(average["kind"] == "RATE_KIND_AVERAGE" and average["value"] == "3.75301",
         f"step 5, the 90-day average of 23 October: {average}")
    [early] = rates(ids["EFFR"], "2026-08-03")["rates"]
    must(early["version"] == 1 and not early["published"],
         f"step 5, a backfilled rate states no published time: {early}")

    # 6. Wants: a Saturday and a day before the recording, declined.
    rates(ids["SOFR"], "2026-10-17")
    rates(ids["SOFR"], "2026-07-31")
    until(90, lambda: store_lake().count("|declined|") >= 2,
          "step 6, the Saturday and the day before the recording were not declined")

    # 7. The lake.
    got = named(store_lake(), codes)
    with open(".e2e/lake", "w", encoding="utf-8") as kept:
        kept.write(got)
    with open("e2e/expected.lake", encoding="utf-8") as held:
        expected = held.read()
    if got != expected:
        diff = subprocess.run(["diff", "-u", "e2e/expected.lake", ".e2e/lake"], capture_output=True, text=True)
        raise Failed(f"step 7, the lake is not e2e/expected.lake:\n{diff.stdout[-3000:]}")

    # 8. A new container records nothing twice.
    compose("up", "-d", "--no-deps", "--force-recreate", "ny-fed")
    runner("ready")
    until(120, lambda: "6 sources, latest Fri 23 Oct" in page("ny-fed", "admin", "/"),
          "step 8, the new container did not read the rates again")
    time.sleep(5)
    again = named(store_lake(), codes)
    must(again == got, "step 8, the new container recorded something twice:\n"
         + subprocess.run(["diff", "-u", "-", ".e2e/lake"], input=again, capture_output=True, text=True).stdout[-2000:])
    logs = compose("logs", "--no-color", "ny-fed").stdout
    must(f"0 recorded, 0 restated, {CURRENT_RATES} unchanged" in logs,
         "step 8, the new container's check was answered unchanged: " + logs[-800:])
    until(90, lambda: all(s["licensed"] for s in call(read_datasets)["served"]),
          "step 8, the new container never read its dataset's licence")

    rows = got.count("row|")
    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: the NY Fed's API "
          f"unreachable said on Connection, nothing recorded; sample data's 13 to 23 October 2026 "
          f"read, the nine records resolved by symbol at nyfed to INS- records, the history "
          f"backfilled from 3 August; read_connection and read_datasets answering what the pages "
          f"show, and core listing {DATASET} as declared; licensed and "
          f"entitled; SOFR (3.90, act/360, percentiles, volume), the SOFR Index and the 90-day "
          f"average read back; a Saturday and 31 July declined source silent; `store lake` as "
          f"e2e/expected.lake ({rows} rows); and a new container recording nothing twice, its "
          f"licence read on start")


def main():
    os.makedirs(".e2e", exist_ok=True)
    open(LOG, "w").close()
    try:
        run()
    except (Failed, subprocess.TimeoutExpired, KeyError, ValueError, IndexError, TypeError) as failed:
        with open(COMPONENTS, "a", encoding="utf-8") as kept:
            kept.write(compose("logs", "--no-color", check=False).stdout)
        compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
        print(f"e2e FAILED: {failed}; the runner's log is in {LOG}, the components' in {COMPONENTS}",
              file=sys.stderr)
        return 1
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
