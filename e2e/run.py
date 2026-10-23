"""`make e2e`: the plugin on the plugin harness of the runtime it pins
(contract v27), as instance `ny-fed`, beside the harness's admin. Run from
the repository's root by the Makefile, which builds the image and writes the
harness's plugins first; standard library only.

The harness's stand-in for the platform's master holds no referential record
by the NY Fed's symbols (it holds SOFR by a test FIGI alone), so each of the
nine records is a miss here, reported and never minted, and no rate is
recorded: what a deployment does before its platform answers. The rates
themselves are proven by the tests, on the SDK's lake.

1. The API unreachable: the plugin's hosts file sends the NY Fed's API
   nowhere, so its first check fails, and Connection says so -- "Not
   answering", the data role's word -- and records nothing.
2. Sample data on (a developer's setting, accepted on the harness): the
   plugin reads the committed answer's last ten days, 13 to 23 October
   2026; each of the nine records is asked of the deployment by its symbol
   at `nyfed`, as a referential record, and reported missing, never minted;
   Connection says "9 records not held", Sources the days the API stated,
   and Datasets each record with why it has none.
3. Parity: through the deployment's MCP, `read_connection` and
   `read_datasets` answer what the pages show, under the data role's names,
   and core's `dashboard__list_datasets` lists `ny-fed:nyfed_rates` as the
   catalogue declares it: rates, push and pull, daily, New York's day ending
   at midnight, no calendar.
4. `store lake` is e2e/expected.lake: the instance's misses, and no row.
5. A new container: it reads the rates again and records nothing; its
   licence read on start.
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


def page(level, path):
    said = runner("page", "--level", level, path)
    status, _, body = said.partition("\n")
    must(status.strip() == "200", f"{path} answered {said[-600:]}")
    return body


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


def run():
    started = time.time()
    compose("--profile", "runner", "down", "-v", "--remove-orphans", check=False)
    compose("up", "-d")
    runner("ready")

    # 1. The API unreachable.
    said = runner("page", "--level", "admin", "/", "--until", "Not answering", "--seconds", "90")
    must("Error" in said, f"step 1, Connection names why the API was not reached: {said[-500:]}")
    lake = store_lake()
    must("row|" not in lake, f"step 1, nothing recorded with the API unreachable: {lake}")

    # 2. Sample data: the nine records asked for, each a miss, never minted.
    runner("settings", "sample_data=true")
    runner("page", "--level", "admin", "/", "--until", "9 records not held", "--seconds", "120")
    datasets = runner("page", "--level", "admin", "/datasets", "--until", "SOFR Index",
                      "--seconds", "60")
    must(datasets.count("not found") >= len(CODES) or datasets.count("badge warn") >= len(CODES),
         f"step 2, Datasets says why each record has no instrument: {datasets[-1500:]}")
    connection = page("admin", "/")
    must("Thu 22 Oct" in connection and "Fri 23 Oct" in connection,
         f"step 2, Sources name the days the API stated: {connection[-1500:]}")
    until(60, lambda: "miss|ny-fed|" in store_lake(), "step 2, the misses were not reported")

    # 3. Parity through the deployment's MCP, and core's view of the catalogue.
    runner("grant", "--level", "admin")
    runner("mcp", "connect", "--covers", "deployment_admin", "--covers", "ny-fed:admin")
    tools = runner("mcp", "list").split()
    read_connection = next((t for t in tools if t.endswith("read_connection")), "")
    read_datasets = next((t for t in tools if t.endswith("read_datasets")), "")
    must(read_connection and read_datasets, f"step 3, the plugin's two tools are listed: {tools}")
    answered = call(read_connection)
    must(answered["latest_day"] == "2026-10-23" and answered["first_day"] == "2026-10-13"
         and answered["mode"] == "Sample data" and answered["credentials"] == []
         and answered["sessions"] is None and answered["said"] == "9 records not held"
         and [s["last_release"] for s in answered["sources"]][:1] == ["2026-10-22"],
         f"step 3, read_connection: {answered}")
    read = call(read_datasets)
    must([r["code"] for r in read["records"]] == CODES
         and all(not r["instrument_id"] and r["miss"] for r in read["records"])
         and read["served"][0]["dataset"] == DATASET and "newyorkfed.org" in read["attribution"],
         f"step 3, read_datasets names each record and why it has none: {read}")
    # The conductor publishes the launched catalogues on a change and every
    # minute: a harness's instance is launched once its sidecar has reported.
    listed = until(90, lambda: {d["dataset"]: d for d in call("dashboard__list_datasets")["datasets"]
                                if d["dataset"] == DATASET},
                   "step 3, core never listed the dataset")
    entry = listed.get(DATASET, {}).get("catalogue_entry", {})
    must(entry.get("modes") == ["push", "pull"] and entry.get("day_time_zone") == "America/New_York"
         and not entry.get("day_end_minute") and entry.get("cadence") == 86400
         and not entry.get("calendar_id") and entry.get("data_types") == ["meridian.v1.Rate"],
         f"step 3, core lists the catalogue as declared: {listed.get(DATASET)}")

    # 4. The lake.
    got = "\n".join(sorted(store_lake().strip().splitlines())) + "\n"
    with open(".e2e/lake", "w", encoding="utf-8") as kept:
        kept.write(got)
    with open("e2e/expected.lake", encoding="utf-8") as held:
        expected = held.read()
    if got != expected:
        diff = subprocess.run(["diff", "-u", "e2e/expected.lake", ".e2e/lake"], capture_output=True, text=True)
        raise Failed(f"step 4, the lake is not e2e/expected.lake:\n{diff.stdout[-3000:]}")

    # 5. A new container records nothing, and reads its licence on start.
    runner("licence", DATASET, "kept=true", "retention_days=0", "derived_use=true", "display=true",
           "personal_use=false", "note=The NY Fed's reference rates, with its notice and disclaimer.")
    compose("up", "-d", "--no-deps", "--force-recreate", "ny-fed")
    runner("ready")
    until(120, lambda: "9 records not held" in page("admin", "/"),
          "step 5, the new container did not read the rates again")
    again = store_lake()
    must("row|" not in again, f"step 5, the new container recorded nothing: {again}")
    until(90, lambda: all(s["licensed"] for s in call(read_datasets)["served"]),
          "step 5, the new container never read its dataset's licence")

    print(f"e2e OK in {int(time.time() - started)}s on the plugin harness: the NY Fed's API "
          f"unreachable said on Connection, nothing recorded; sample data's 13 to 23 October 2026 "
          f"read, each of the nine records asked for by its symbol at nyfed and reported missing, "
          f"never minted, nothing recorded; read_connection and read_datasets answering what the "
          f"pages show, and core listing {DATASET} as declared; `store lake` as e2e/expected.lake; "
          f"and a new container recording nothing, its licence read on start")


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
