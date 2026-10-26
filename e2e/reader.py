"""A reading plugin for the e2e, on the Python SDK: the deployment's view of
what this plugin recorded, as a `reporting` plugin entitled to its dataset
reads it (W10.6). Not the plugin, and never shipped: the e2e runs it from
this directory in the plugin's own image, which carries the SDK.

It answers its page as JSON, so the harness's runner can read it
(`page --instance reader --level read PATH`):

  /rates?subject=ID&date=D[&dataset=D]
      one read by business date: each rate's dataset, row key, version,
      business date, kind, value and unit as text, convention, percentiles,
      volume and published times; and what the lake left unanswered, with why.

Standard library and the SDK only; every figure stays text, never a float.
"""
import asyncio
import http.server
import json
import threading
import urllib.parse

import meridian
from meridian import Interface, Page, SourceChoice
from meridian.operations import as_decimal
from meridian.plugin.v1 import operations_pb2 as ops

PORT = 8088
LOOP = asyncio.new_event_loop()


def rate_json(rate):
    meta = rate.meta
    return {
        "dataset": meta.source.dataset,
        "row_key": meta.row_key,
        "version": meta.version,
        "business_date": meta.business_date,
        "subject": meta.subjects[0].entity_id if meta.subjects else "",
        "kind": ops.RateKind.Name(rate.kind),
        "value": str(as_decimal(rate.value.value)),
        "unit": ops.ValueUnit.Name(rate.value.unit),
        "index_base": rate.value.index_base,
        "day_count": ops.DayCount.Name(rate.convention.day_count) if rate.HasField("convention") else "",
        "compounding": ops.Compounding.Name(rate.convention.compounding) if rate.HasField("convention") else "",
        "percentiles": {str(p.percentile): str(as_decimal(p.value)) for p in rate.percentiles},
        "volume": str(as_decimal(rate.volume.amount)) if rate.HasField("volume") else "",
        "published": [t.at_ns for t in meta.source_times if t.kind == ops.SOURCE_TIME_KIND_PUBLISHED],
        "raw": meta.raw.key if meta.HasField("raw") else "",
    }


class Reader:
    def __init__(self, plugin):
        self.plugin = plugin

    async def rates(self, query):
        one = lambda name: query.get(name, [""])[0]  # noqa: E731
        asked = {"subjects": [meridian.SubjectRef(entity_id=s) for s in query.get("subject", [])]}
        if one("dataset"):
            asked["sources"] = SourceChoice(named=query["dataset"])
        if one("date"):
            asked["business_date"] = one("date")
        answer = await self.plugin.list_rates(**asked)
        return {
            "rates": [rate_json(r) for r in answer.rates],
            "unanswered": [
                {"subject": u.subject.entity_id, "dataset": u.dataset,
                 "reason": ops.UnansweredReason.Name(u.reason)}
                for u in answer.unanswered
            ],
        }

    async def answer(self, path, query):
        if path == "/rates":
            return await self.rates(query)
        return {"page": "the e2e's reader"}


def serve(reader):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            future = asyncio.run_coroutine_threadsafe(
                reader.answer(parsed.path, urllib.parse.parse_qs(parsed.query)), LOOP)
            try:
                body, status = json.dumps(future.result(timeout=60), sort_keys=True), 200
            except Exception as failed:  # said on the page, for the run to quote
                body, status = json.dumps({"failed": f"{type(failed).__name__}: {failed}"}), 500
            data = body.encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *_args):
            pass

    http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


#: What the stand-in registers, its whole declaration (contract v25): the
#: e2e prints it with meridian-declaration and the harness holds the
#: stand-in's registration to it.
DECLARATION = meridian.Declaration(
    interface=Interface(PORT, "The e2e's reader", pages=[Page("/", "Rates", levels=["read"])])
)


async def main():
    plugin = await meridian.connect(declaration=DECLARATION)
    print(f"reader registered as {plugin.identity.instance_id}", flush=True)
    threading.Thread(target=serve, args=(Reader(plugin),), daemon=True).start()
    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.set_event_loop(LOOP)
    LOOP.run_until_complete(main())
