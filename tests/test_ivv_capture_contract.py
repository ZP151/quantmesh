"""Owned scripted vectors only; never imports or connects a real SDK."""

import copy
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

FILE = Path(__file__).resolve().parents[1] / "tools/research/capture_opend_ivv_daily.py"
SCHEDULE = [
    {
        "close": "2026-05-08T20:00:00+00:00",
        "date": "2026-05-08",
        "open": "2026-05-08T13:30:00+00:00",
    },
    {
        "close": "2026-05-11T20:00:00+00:00",
        "date": "2026-05-11",
        "open": "2026-05-11T13:30:00+00:00",
    },
    {
        "close": "2026-05-12T20:00:00+00:00",
        "date": "2026-05-12",
        "open": "2026-05-12T13:30:00+00:00",
    },
    {
        "close": "2026-05-13T20:00:00+00:00",
        "date": "2026-05-13",
        "open": "2026-05-13T13:30:00+00:00",
    },
    {
        "close": "2026-05-14T20:00:00+00:00",
        "date": "2026-05-14",
        "open": "2026-05-14T13:30:00+00:00",
    },
    {
        "close": "2026-05-15T20:00:00+00:00",
        "date": "2026-05-15",
        "open": "2026-05-15T13:30:00+00:00",
    },
    {
        "close": "2026-05-18T20:00:00+00:00",
        "date": "2026-05-18",
        "open": "2026-05-18T13:30:00+00:00",
    },
    {
        "close": "2026-05-19T20:00:00+00:00",
        "date": "2026-05-19",
        "open": "2026-05-19T13:30:00+00:00",
    },
    {
        "close": "2026-05-20T20:00:00+00:00",
        "date": "2026-05-20",
        "open": "2026-05-20T13:30:00+00:00",
    },
    {
        "close": "2026-05-21T20:00:00+00:00",
        "date": "2026-05-21",
        "open": "2026-05-21T13:30:00+00:00",
    },
    {
        "close": "2026-05-22T20:00:00+00:00",
        "date": "2026-05-22",
        "open": "2026-05-22T13:30:00+00:00",
    },
    {
        "close": "2026-05-26T20:00:00+00:00",
        "date": "2026-05-26",
        "open": "2026-05-26T13:30:00+00:00",
    },
    {
        "close": "2026-05-27T20:00:00+00:00",
        "date": "2026-05-27",
        "open": "2026-05-27T13:30:00+00:00",
    },
    {
        "close": "2026-05-28T20:00:00+00:00",
        "date": "2026-05-28",
        "open": "2026-05-28T13:30:00+00:00",
    },
    {
        "close": "2026-05-29T20:00:00+00:00",
        "date": "2026-05-29",
        "open": "2026-05-29T13:30:00+00:00",
    },
    {
        "close": "2026-06-01T20:00:00+00:00",
        "date": "2026-06-01",
        "open": "2026-06-01T13:30:00+00:00",
    },
    {
        "close": "2026-06-02T20:00:00+00:00",
        "date": "2026-06-02",
        "open": "2026-06-02T13:30:00+00:00",
    },
    {
        "close": "2026-06-03T20:00:00+00:00",
        "date": "2026-06-03",
        "open": "2026-06-03T13:30:00+00:00",
    },
    {
        "close": "2026-06-04T20:00:00+00:00",
        "date": "2026-06-04",
        "open": "2026-06-04T13:30:00+00:00",
    },
    {
        "close": "2026-06-05T20:00:00+00:00",
        "date": "2026-06-05",
        "open": "2026-06-05T13:30:00+00:00",
    },
    {
        "close": "2026-06-08T20:00:00+00:00",
        "date": "2026-06-08",
        "open": "2026-06-08T13:30:00+00:00",
    },
    {
        "close": "2026-06-09T20:00:00+00:00",
        "date": "2026-06-09",
        "open": "2026-06-09T13:30:00+00:00",
    },
    {
        "close": "2026-06-10T20:00:00+00:00",
        "date": "2026-06-10",
        "open": "2026-06-10T13:30:00+00:00",
    },
    {
        "close": "2026-06-11T20:00:00+00:00",
        "date": "2026-06-11",
        "open": "2026-06-11T13:30:00+00:00",
    },
    {
        "close": "2026-06-12T20:00:00+00:00",
        "date": "2026-06-12",
        "open": "2026-06-12T13:30:00+00:00",
    },
    {
        "close": "2026-06-15T20:00:00+00:00",
        "date": "2026-06-15",
        "open": "2026-06-15T13:30:00+00:00",
    },
    {
        "close": "2026-06-16T20:00:00+00:00",
        "date": "2026-06-16",
        "open": "2026-06-16T13:30:00+00:00",
    },
    {
        "close": "2026-06-17T20:00:00+00:00",
        "date": "2026-06-17",
        "open": "2026-06-17T13:30:00+00:00",
    },
    {
        "close": "2026-06-18T20:00:00+00:00",
        "date": "2026-06-18",
        "open": "2026-06-18T13:30:00+00:00",
    },
    {
        "close": "2026-06-22T20:00:00+00:00",
        "date": "2026-06-22",
        "open": "2026-06-22T13:30:00+00:00",
    },
    {
        "close": "2026-06-23T20:00:00+00:00",
        "date": "2026-06-23",
        "open": "2026-06-23T13:30:00+00:00",
    },
    {
        "close": "2026-06-24T20:00:00+00:00",
        "date": "2026-06-24",
        "open": "2026-06-24T13:30:00+00:00",
    },
    {
        "close": "2026-06-25T20:00:00+00:00",
        "date": "2026-06-25",
        "open": "2026-06-25T13:30:00+00:00",
    },
    {
        "close": "2026-06-26T20:00:00+00:00",
        "date": "2026-06-26",
        "open": "2026-06-26T13:30:00+00:00",
    },
    {
        "close": "2026-06-29T20:00:00+00:00",
        "date": "2026-06-29",
        "open": "2026-06-29T13:30:00+00:00",
    },
    {
        "close": "2026-06-30T20:00:00+00:00",
        "date": "2026-06-30",
        "open": "2026-06-30T13:30:00+00:00",
    },
    {
        "close": "2026-07-01T20:00:00+00:00",
        "date": "2026-07-01",
        "open": "2026-07-01T13:30:00+00:00",
    },
    {
        "close": "2026-07-02T20:00:00+00:00",
        "date": "2026-07-02",
        "open": "2026-07-02T13:30:00+00:00",
    },
    {
        "close": "2026-07-06T20:00:00+00:00",
        "date": "2026-07-06",
        "open": "2026-07-06T13:30:00+00:00",
    },
    {
        "close": "2026-07-07T20:00:00+00:00",
        "date": "2026-07-07",
        "open": "2026-07-07T13:30:00+00:00",
    },
    {
        "close": "2026-07-08T20:00:00+00:00",
        "date": "2026-07-08",
        "open": "2026-07-08T13:30:00+00:00",
    },
    {
        "close": "2026-07-09T20:00:00+00:00",
        "date": "2026-07-09",
        "open": "2026-07-09T13:30:00+00:00",
    },
    {
        "close": "2026-07-10T20:00:00+00:00",
        "date": "2026-07-10",
        "open": "2026-07-10T13:30:00+00:00",
    },
    {
        "close": "2026-07-13T20:00:00+00:00",
        "date": "2026-07-13",
        "open": "2026-07-13T13:30:00+00:00",
    },
    {
        "close": "2026-07-14T20:00:00+00:00",
        "date": "2026-07-14",
        "open": "2026-07-14T13:30:00+00:00",
    },
    {
        "close": "2026-07-15T20:00:00+00:00",
        "date": "2026-07-15",
        "open": "2026-07-15T13:30:00+00:00",
    },
    {
        "close": "2026-07-16T20:00:00+00:00",
        "date": "2026-07-16",
        "open": "2026-07-16T13:30:00+00:00",
    },
    {
        "close": "2026-07-17T20:00:00+00:00",
        "date": "2026-07-17",
        "open": "2026-07-17T13:30:00+00:00",
    },
    {
        "close": "2026-07-20T20:00:00+00:00",
        "date": "2026-07-20",
        "open": "2026-07-20T13:30:00+00:00",
    },
    {
        "close": "2026-07-21T20:00:00+00:00",
        "date": "2026-07-21",
        "open": "2026-07-21T13:30:00+00:00",
    },
    {
        "close": "2026-07-22T20:00:00+00:00",
        "date": "2026-07-22",
        "open": "2026-07-22T13:30:00+00:00",
    },
    {
        "close": "2026-07-23T20:00:00+00:00",
        "date": "2026-07-23",
        "open": "2026-07-23T13:30:00+00:00",
    },
    {
        "close": "2026-07-24T20:00:00+00:00",
        "date": "2026-07-24",
        "open": "2026-07-24T13:30:00+00:00",
    },
    {
        "close": "2026-07-27T20:00:00+00:00",
        "date": "2026-07-27",
        "open": "2026-07-27T13:30:00+00:00",
    },
    {
        "close": "2026-07-28T20:00:00+00:00",
        "date": "2026-07-28",
        "open": "2026-07-28T13:30:00+00:00",
    },
    {
        "close": "2026-07-29T20:00:00+00:00",
        "date": "2026-07-29",
        "open": "2026-07-29T13:30:00+00:00",
    },
    {
        "close": "2026-07-30T20:00:00+00:00",
        "date": "2026-07-30",
        "open": "2026-07-30T13:30:00+00:00",
    },
    {
        "close": "2026-07-31T20:00:00+00:00",
        "date": "2026-07-31",
        "open": "2026-07-31T13:30:00+00:00",
    },
    {
        "close": "2026-08-03T20:00:00+00:00",
        "date": "2026-08-03",
        "open": "2026-08-03T13:30:00+00:00",
    },
    {
        "close": "2026-08-04T20:00:00+00:00",
        "date": "2026-08-04",
        "open": "2026-08-04T13:30:00+00:00",
    },
    {
        "close": "2026-08-05T20:00:00+00:00",
        "date": "2026-08-05",
        "open": "2026-08-05T13:30:00+00:00",
    },
    {
        "close": "2026-08-06T20:00:00+00:00",
        "date": "2026-08-06",
        "open": "2026-08-06T13:30:00+00:00",
    },
    {
        "close": "2026-08-07T20:00:00+00:00",
        "date": "2026-08-07",
        "open": "2026-08-07T13:30:00+00:00",
    },
    {
        "close": "2026-08-10T20:00:00+00:00",
        "date": "2026-08-10",
        "open": "2026-08-10T13:30:00+00:00",
    },
    {
        "close": "2026-08-11T20:00:00+00:00",
        "date": "2026-08-11",
        "open": "2026-08-11T13:30:00+00:00",
    },
    {
        "close": "2026-08-12T20:00:00+00:00",
        "date": "2026-08-12",
        "open": "2026-08-12T13:30:00+00:00",
    },
    {
        "close": "2026-08-13T20:00:00+00:00",
        "date": "2026-08-13",
        "open": "2026-08-13T13:30:00+00:00",
    },
    {
        "close": "2026-08-14T20:00:00+00:00",
        "date": "2026-08-14",
        "open": "2026-08-14T13:30:00+00:00",
    },
    {
        "close": "2026-08-17T20:00:00+00:00",
        "date": "2026-08-17",
        "open": "2026-08-17T13:30:00+00:00",
    },
    {
        "close": "2026-08-18T20:00:00+00:00",
        "date": "2026-08-18",
        "open": "2026-08-18T13:30:00+00:00",
    },
    {
        "close": "2026-08-19T20:00:00+00:00",
        "date": "2026-08-19",
        "open": "2026-08-19T13:30:00+00:00",
    },
    {
        "close": "2026-08-20T20:00:00+00:00",
        "date": "2026-08-20",
        "open": "2026-08-20T13:30:00+00:00",
    },
    {
        "close": "2026-08-21T20:00:00+00:00",
        "date": "2026-08-21",
        "open": "2026-08-21T13:30:00+00:00",
    },
    {
        "close": "2026-08-24T20:00:00+00:00",
        "date": "2026-08-24",
        "open": "2026-08-24T13:30:00+00:00",
    },
    {
        "close": "2026-08-25T20:00:00+00:00",
        "date": "2026-08-25",
        "open": "2026-08-25T13:30:00+00:00",
    },
    {
        "close": "2026-08-26T20:00:00+00:00",
        "date": "2026-08-26",
        "open": "2026-08-26T13:30:00+00:00",
    },
    {
        "close": "2026-08-27T20:00:00+00:00",
        "date": "2026-08-27",
        "open": "2026-08-27T13:30:00+00:00",
    },
    {
        "close": "2026-08-28T20:00:00+00:00",
        "date": "2026-08-28",
        "open": "2026-08-28T13:30:00+00:00",
    },
    {
        "close": "2026-08-31T20:00:00+00:00",
        "date": "2026-08-31",
        "open": "2026-08-31T13:30:00+00:00",
    },
    {
        "close": "2026-09-01T20:00:00+00:00",
        "date": "2026-09-01",
        "open": "2026-09-01T13:30:00+00:00",
    },
    {
        "close": "2026-09-02T20:00:00+00:00",
        "date": "2026-09-02",
        "open": "2026-09-02T13:30:00+00:00",
    },
    {
        "close": "2026-09-03T20:00:00+00:00",
        "date": "2026-09-03",
        "open": "2026-09-03T13:30:00+00:00",
    },
    {
        "close": "2026-09-04T20:00:00+00:00",
        "date": "2026-09-04",
        "open": "2026-09-04T13:30:00+00:00",
    },
    {
        "close": "2026-09-08T20:00:00+00:00",
        "date": "2026-09-08",
        "open": "2026-09-08T13:30:00+00:00",
    },
    {
        "close": "2026-09-09T20:00:00+00:00",
        "date": "2026-09-09",
        "open": "2026-09-09T13:30:00+00:00",
    },
    {
        "close": "2026-09-10T20:00:00+00:00",
        "date": "2026-09-10",
        "open": "2026-09-10T13:30:00+00:00",
    },
    {
        "close": "2026-09-11T20:00:00+00:00",
        "date": "2026-09-11",
        "open": "2026-09-11T13:30:00+00:00",
    },
    {
        "close": "2026-09-14T20:00:00+00:00",
        "date": "2026-09-14",
        "open": "2026-09-14T13:30:00+00:00",
    },
    {
        "close": "2026-09-15T20:00:00+00:00",
        "date": "2026-09-15",
        "open": "2026-09-15T13:30:00+00:00",
    },
    {
        "close": "2026-09-16T20:00:00+00:00",
        "date": "2026-09-16",
        "open": "2026-09-16T13:30:00+00:00",
    },
    {
        "close": "2026-09-17T20:00:00+00:00",
        "date": "2026-09-17",
        "open": "2026-09-17T13:30:00+00:00",
    },
    {
        "close": "2026-09-18T20:00:00+00:00",
        "date": "2026-09-18",
        "open": "2026-09-18T13:30:00+00:00",
    },
    {
        "close": "2026-09-21T20:00:00+00:00",
        "date": "2026-09-21",
        "open": "2026-09-21T13:30:00+00:00",
    },
    {
        "close": "2026-09-22T20:00:00+00:00",
        "date": "2026-09-22",
        "open": "2026-09-22T13:30:00+00:00",
    },
    {
        "close": "2026-09-23T20:00:00+00:00",
        "date": "2026-09-23",
        "open": "2026-09-23T13:30:00+00:00",
    },
    {
        "close": "2026-09-24T20:00:00+00:00",
        "date": "2026-09-24",
        "open": "2026-09-24T13:30:00+00:00",
    },
    {
        "close": "2026-09-25T20:00:00+00:00",
        "date": "2026-09-25",
        "open": "2026-09-25T13:30:00+00:00",
    },
    {
        "close": "2026-09-28T20:00:00+00:00",
        "date": "2026-09-28",
        "open": "2026-09-28T13:30:00+00:00",
    },
    {
        "close": "2026-09-29T20:00:00+00:00",
        "date": "2026-09-29",
        "open": "2026-09-29T13:30:00+00:00",
    },
    {
        "close": "2026-09-30T20:00:00+00:00",
        "date": "2026-09-30",
        "open": "2026-09-30T13:30:00+00:00",
    },
    {
        "close": "2026-10-01T20:00:00+00:00",
        "date": "2026-10-01",
        "open": "2026-10-01T13:30:00+00:00",
    },
    {
        "close": "2026-10-02T20:00:00+00:00",
        "date": "2026-10-02",
        "open": "2026-10-02T13:30:00+00:00",
    },
    {
        "close": "2026-10-05T20:00:00+00:00",
        "date": "2026-10-05",
        "open": "2026-10-05T13:30:00+00:00",
    },
    {
        "close": "2026-10-06T20:00:00+00:00",
        "date": "2026-10-06",
        "open": "2026-10-06T13:30:00+00:00",
    },
    {
        "close": "2026-10-07T20:00:00+00:00",
        "date": "2026-10-07",
        "open": "2026-10-07T13:30:00+00:00",
    },
    {
        "close": "2026-10-08T20:00:00+00:00",
        "date": "2026-10-08",
        "open": "2026-10-08T13:30:00+00:00",
    },
    {
        "close": "2026-10-09T20:00:00+00:00",
        "date": "2026-10-09",
        "open": "2026-10-09T13:30:00+00:00",
    },
    {
        "close": "2026-10-12T20:00:00+00:00",
        "date": "2026-10-12",
        "open": "2026-10-12T13:30:00+00:00",
    },
    {
        "close": "2026-10-13T20:00:00+00:00",
        "date": "2026-10-13",
        "open": "2026-10-13T13:30:00+00:00",
    },
    {
        "close": "2026-10-14T20:00:00+00:00",
        "date": "2026-10-14",
        "open": "2026-10-14T13:30:00+00:00",
    },
    {
        "close": "2026-10-15T20:00:00+00:00",
        "date": "2026-10-15",
        "open": "2026-10-15T13:30:00+00:00",
    },
    {
        "close": "2026-10-16T20:00:00+00:00",
        "date": "2026-10-16",
        "open": "2026-10-16T13:30:00+00:00",
    },
    {
        "close": "2026-10-19T20:00:00+00:00",
        "date": "2026-10-19",
        "open": "2026-10-19T13:30:00+00:00",
    },
    {
        "close": "2026-10-20T20:00:00+00:00",
        "date": "2026-10-20",
        "open": "2026-10-20T13:30:00+00:00",
    },
    {
        "close": "2026-10-21T20:00:00+00:00",
        "date": "2026-10-21",
        "open": "2026-10-21T13:30:00+00:00",
    },
    {
        "close": "2026-10-22T20:00:00+00:00",
        "date": "2026-10-22",
        "open": "2026-10-22T13:30:00+00:00",
    },
    {
        "close": "2026-10-23T20:00:00+00:00",
        "date": "2026-10-23",
        "open": "2026-10-23T13:30:00+00:00",
    },
    {
        "close": "2026-10-26T20:00:00+00:00",
        "date": "2026-10-26",
        "open": "2026-10-26T13:30:00+00:00",
    },
    {
        "close": "2026-10-27T20:00:00+00:00",
        "date": "2026-10-27",
        "open": "2026-10-27T13:30:00+00:00",
    },
    {
        "close": "2026-10-28T20:00:00+00:00",
        "date": "2026-10-28",
        "open": "2026-10-28T13:30:00+00:00",
    },
    {
        "close": "2026-10-29T20:00:00+00:00",
        "date": "2026-10-29",
        "open": "2026-10-29T13:30:00+00:00",
    },
]
DATES = [x["date"] for x in SCHEDULE]


def leaf():
    if not FILE.exists():
        return SimpleNamespace()
    spec = importlib.util.spec_from_file_location("qm_ivv_capture_leaf", FILE)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def row(**raw):
    return {"raw": raw, "presence": sorted(raw)}


def originals():
    return {
        "schema_id": "qm.ivv.capture-plain.v1",
        "symbol": "US.IVV",
        "scope_id": "e28541ddae3d7b567e23e2963cc454995aa01c420bd567d8eb8aace6b6354f07",
        "raw_source_hashes": {
            x: str(i) * 64 for i, x in enumerate(("history", "rehab", "dividends", "splits"), 1)
        },
        "history_pages": [
            {
                "code": "US.IVV",
                "autype": "None",
                "interval": "1d",
                "next_page_req_key": None,
                "next_key_has_field": False,
                "rows": [
                    row(
                        time=d + " 00:00:00",
                        isBlank=False,
                        openPrice=10.0,
                        highPrice=12.0,
                        lowPrice=9.0,
                        closePrice=11.0,
                        volume=1000,
                    )
                    for d in DATES
                ],
            }
        ],
        "adjustment_factors": {"code": "US.IVV", "rows": []},
        "dividends": {"code": "US.IVV", "rows": []},
        "stock_split_pages": [
            {"code": "US.IVV", "next_key": "-1", "next_key_has_field": True, "rows": []}
        ],
    }


def facts(m, data):
    return {
        "capture_evidence_sha256": m.capture_evidence_digest(data),
        "price_currency": "USD",
        "volume_unit": "shares",
        "volume_venue": "DECLARED_OWNED_FIXTURE_NOT_REAL_FEED",
        "coverage_start": DATES[0],
        "coverage_end": DATES[-1],
        "evidence_refs": ["a" * 64],
    }


def test_public_entry_and_pure_normalizer_exist_without_sdk_import():
    m = leaf()
    assert hasattr(m, "capture_once"), "approved IVV helper is not implemented"
    assert hasattr(m, "normalize_capture")
    assert "moomoo" not in sys.modules


def test_owned_raw_rows_normalize_without_qualifying_source():
    m = leaf()
    data = originals()
    result = m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))
    assert len(result["bars"]) == 121
    assert result["bars"][0] == {
        "date": DATES[0],
        "open": 10.0,
        "high": 12.0,
        "low": 9.0,
        "close": 11.0,
        "volume": 1000.0,
        "dividend": 0.0,
    }
    assert result["schedule"] == SCHEDULE
    assert result["distributions"] == []
    assert result["status"] == "NORMALIZED_UNREVIEWED"
    assert "qualified" not in result


@pytest.mark.parametrize(
    "field",
    [
        "price_currency",
        "volume_unit",
        "volume_venue",
        "evidence_refs",
        "coverage_start",
        "capture_evidence_sha256",
    ],
)
def test_source_fact_parameters_do_not_default_to_evidence(field):
    m = leaf()
    data = originals()
    evidence = facts(m, data)
    evidence.pop(field)
    with pytest.raises(m.CaptureRejected, match="source_facts"):
        m.normalize_capture(data, schedule=SCHEDULE, source_facts=evidence)


def test_warmup_cash_pay_after_terminal_is_preserved_and_bar_cash_matches():
    m = leaf()
    data = originals()
    day = DATES[3]
    data["adjustment_factors"]["rows"] = [row(time=day, companyActFlag=64, dividend=1.25)]
    data["dividends"]["rows"] = [
        row(
            exDate=day.replace("-", "/"),
            dividendPayableDate="2026/11/04",
            statement="USD 1.25 per share",
        )
    ]
    result = m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))
    assert result["distributions"] == [{"ex_date": day, "pay_date": "2026-11-04", "amount": 1.25}]
    assert result["bars"][3]["dividend"] == 1.25
    assert sum(x["dividend"] for x in result["bars"]) == 1.25


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["history_pages"][0]["rows"][1]["raw"].pop("openPrice"),
        lambda d: d["history_pages"][0]["rows"][1].update(presence=[]),
        lambda d: d["history_pages"][0]["rows"][1]["raw"].update(isBlank=True),
        lambda d: d["history_pages"][0]["rows"][1]["raw"].update(volume=float("nan")),
        lambda d: d["history_pages"][0]["rows"][1]["raw"].update(hpVolume=1000.5),
        lambda d: d["history_pages"][0].update(next_key_has_field=True),
        lambda d: d["stock_split_pages"][0].update(next_key_has_field=False),
        lambda d: d["stock_split_pages"][0].update(next_key="opaque-next"),
        lambda d: d["history_pages"][0]["rows"].pop(),
        lambda d: d["history_pages"][0]["rows"].append(d["history_pages"][0]["rows"][0]),
    ],
)
def test_presence_carry_blanks_paging_missing_sessions_and_units_fail(mutate):
    m = leaf()
    data = originals()
    mutate(data)
    with pytest.raises(m.CaptureRejected):
        m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))


@pytest.mark.parametrize(
    "change",
    ["missing_pay", "ambiguous_join", "currency_guess", "amount_conflict", "unsupported_split"],
)
def test_cash_fidelity_never_guesses(change):
    m = leaf()
    data = originals()
    day = DATES[3]
    data["adjustment_factors"]["rows"] = [row(time=day, companyActFlag=64, dividend=1.25)]
    cash = row(exDate=day, dividendPayableDate=DATES[5], statement="USD 1.25 per share")
    data["dividends"]["rows"] = [cash]
    if change == "missing_pay":
        cash["raw"].pop("dividendPayableDate")
        cash["presence"].remove("dividendPayableDate")
    if change == "ambiguous_join":
        data["dividends"]["rows"].append(copy.deepcopy(cash))
    if change == "currency_guess":
        cash["raw"]["statement"] = "$1.25"
    if change == "amount_conflict":
        cash["raw"]["statement"] = "USD 1.50 per share"
    if change == "unsupported_split":
        data["adjustment_factors"]["rows"][0] = row(time=day, companyActFlag=65, dividend=1.25)
    with pytest.raises(m.CaptureRejected):
        m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))


def test_fixed_schedule_does_not_slide_with_asof():
    m = leaf()
    data = originals()
    changed = copy.deepcopy(SCHEDULE)
    changed[-1]["date"] = "2026-10-30"
    with pytest.raises(m.CaptureRejected, match="schedule"):
        m.normalize_capture(data, schedule=changed, source_facts=facts(m, data))


class Clock:
    def __init__(self):
        self.value = 0.0

    def mono(self):
        return self.value

    def wall(self):
        from datetime import UTC, datetime, timedelta

        return datetime(2026, 10, 30, 15, tzinfo=UTC) + timedelta(seconds=self.value)

    def sleep(self, n):
        self.value += n


def contract(m):
    return {
        "schema_id": "qm.ivv.capture-plan.v1",
        "scope_id": m.SCOPE,
        "symbol": "US.IVV",
        "approval_sha256": m.APPROVAL,
        "execution_sha256": m.EXECUTION,
        "input_window_digest": m.WINDOW,
        "full_window_sha256": m.FULL_WINDOW,
        "effect_id": "owned-synthetic-vector",
        "capture_helper_sha256": "a" * 64,
        "catalog_sha256": "b" * 64,
        "sdk_pins_sha256": "c" * 64,
        "started_monotonic": 0.0,
        "endpoint": {
            "host": "127.0.0.1",
            "port": 11112,
            "is_encrypt": False,
            "security_firm": "NONE",
        },
    }


class ScriptedBackend:
    """A fixed fake transport, never a real SDK or socket."""

    def __init__(self, m, observer, writer, clock, root, *, mode=None):
        self.m = m
        self.o = observer
        self.writer = writer
        self.clock = clock
        self.root = root
        self.mode = mode
        self.closed = False
        self.close_calls = 0
        data = originals()
        self.trees = {
            "rehab": {
                "retType": 0,
                "s2c": {"rehabList": [{"time": DATES[3], "companyActFlag": 64, "dividend": 1.25}]},
            },
            "dividends": {
                "retType": 0,
                "s2c": {
                    "dividendList": [
                        {
                            "exDate": DATES[3],
                            "dividendPayableDate": DATES[5],
                            "statement": "USD 1.25 per share",
                        }
                    ]
                },
            },
            "splits": {"retType": 0, "s2c": {"splitItemList": [], "nextKey": "-1"}},
            "history": {
                "retType": 0,
                "s2c": {
                    "security": {"market": 11, "code": "IVV"},
                    "klList": [x["raw"] for x in data["history_pages"][0]["rows"]],
                },
            },
        }

    def open(self):
        intent = json.loads((self.root / "capture-intent.json").read_bytes())
        assert intent["state"] == "ATTEMPTED" and intent["synthetic"] is True
        self.o.context_created()
        self.o.initializing()
        if self.mode == "reconnect":
            self.o.initializing()

    def invoke(self, tag, params):
        self.o.reserve(tag, params)
        serial = len(self.o.pack_attempts)
        self.o.register(tag, self.m.RPCS[tag], serial)
        self.o.before_send(self.m.RPCS[tag], serial)
        if tag == "state":
            return {
                "qot_logined": True,
                "server_ver": "10.10.7008",
                "timestamp": str(self.clock.wall().timestamp()),
                "user_id": "NEVER_PERSIST",
            }
        if tag == "quota":
            return {"used": 0, "remaining": 5, "private_details": "NEVER_PERSIST"}
        if tag == "basic":
            return {
                "code": "US.IVV",
                "stock_type": "ETF",
                "lot_size": 1,
                "exchange_type": "FIXTURE",
            }
        if self.mode == "unknown_send" and tag == "rehab":
            raise RuntimeError("SECRET_ERROR_TEXT")
        tree = copy.deepcopy(self.trees[tag])
        if self.mode == "split_missing" and tag == "splits":
            tree["s2c"].pop("nextKey")
        raw = json.dumps(tree, sort_keys=True, separators=(",", ":")).encode()
        if self.mode == "oversize" and tag == "rehab":
            raw = b"x" * (self.m.MIB + 1)
        self.o.response(tag, raw, tree, "US.IVV" if tag == "history" else None)
        if self.mode == "paging" and tag == "history":
            self.o.reserve(tag, params)  # second hidden public-method page blocked BEFORE send
        if self.mode == "stale" and tag == "splits":
            self.clock.value += 301
        return None

    def close(self):
        self.close_calls += 1
        if self.mode == "close_raises":
            raise RuntimeError("CLOSE_PRIVATE_TEXT")
        self.closed = self.mode != "close_stuck"

    def close_evidence(self):
        return {
            "context_closed": self.closed,
            "callbacks_stopped": self.closed,
            "data_socket_closed": self.closed,
        }


def run_scripted(m, root, *, mode=None, sync=None):
    clock = Clock()
    made = []

    def factory(observer, writer, plan, given_clock):
        assert (root / "capture-intent.json").exists(), "SDK factory preceded durable intent"
        b = ScriptedBackend(m, observer, writer, clock, root, mode=mode)
        made.append(b)
        return b

    result = m._run_capture(
        contract(m),
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=sync or (lambda p: None),
        synthetic=True,
        dates=DATES,
    )
    return result, made, clock


def test_capture_core_available_only_behind_production_permit(tmp_path):
    m = leaf()
    assert hasattr(m, "_run_capture"), "bounded scripted capture core is missing"
    with pytest.raises(m.CaptureRejected):
        m.capture_once(tmp_path / "plan.json", tmp_path / "real")
    assert not (tmp_path / "real").exists()


def test_durable_intent_precedes_factory_and_complete_capture_is_unreviewed(tmp_path):
    m = leaf()
    root = tmp_path / "OWNED_SYNTHETIC"
    events = []
    result, made, _ = run_scripted(m, root, sync=lambda p: events.append(p))
    assert events
    assert result["state"] == "CAPTURED_UNREVIEWED"
    assert result["requires_parent_close_receipt"] is True
    assert result["normal_close"] == {
        "context_closed": True,
        "callbacks_stopped": True,
        "data_socket_closed": True,
    }
    assert result["counts"]["application_sends"] == 7
    assert result["counts"]["history_sends"] == 1
    assert made[0].close_calls == 1
    assert len(result["responses"]) == 4
    assert "NEVER_PERSIST" not in b"".join(
        p.read_bytes() for p in root.iterdir() if p.is_file()
    ).decode(errors="replace")
    assert "qualified" not in result
    assert "moomoo" not in sys.modules
    plain = json.loads((root / result["plain_ref"]["path"]).read_bytes())
    assert len(plain["history_pages"][0]["rows"]) == 121
    for ref in [
        result["plain_ref"],
        *[v[k] for v in result["responses"].values() for k in ("sdk_ref", "fields_ref")],
    ]:
        b = (root / ref["path"]).read_bytes()
        assert len(b) == ref["bytes"] and hashlib.sha256(b).hexdigest() == ref["sha256"]


def test_spent_path_cannot_get_a_second_context(tmp_path):
    m = leaf()
    root = tmp_path / "OWNED_SYNTHETIC"
    run_scripted(m, root)
    with pytest.raises(m.CaptureRejected, match="spent"):
        run_scripted(m, root)


@pytest.mark.parametrize(
    "mode",
    [
        "reconnect",
        "paging",
        "unknown_send",
        "oversize",
        "split_missing",
        "stale",
        "close_stuck",
        "close_raises",
    ],
)
def test_partial_unknown_and_forced_close_never_form_usable_capture(tmp_path, mode):
    m = leaf()
    root = tmp_path / "OWNED_SYNTHETIC"
    result, made, _ = run_scripted(m, root, mode=mode)
    assert result["state"].startswith("FAILED")
    assert result["counts"]["history_sends"] <= 1 and result["counts"]["application_sends"] <= 7
    assert made[0].close_calls == 1
    assert "SECRET_ERROR_TEXT" not in json.dumps(result) and "CLOSE_PRIVATE_TEXT" not in json.dumps(
        result
    )
    assert (root / "capture-intent.json").exists()
    assert result["requires_parent_close_receipt"] is True


def test_primary_error_is_not_replaced_by_close_error(tmp_path):
    m = leaf()
    clock = Clock()
    root = tmp_path / "OWNED_SYNTHETIC"

    def factory(o, w, p, c):
        b = ScriptedBackend(m, o, w, c, root, mode="unknown_send")

        def fail_close():
            raise RuntimeError("PRIVATE_CLOSE")

        b.close = fail_close
        return b

    result = m._run_capture(
        contract(m),
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=lambda p: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["primary_failure"]["stage"] == "rehab"
    assert result["close_failure"]["stage"] == "close"


def test_window_effect_scope_or_runtime_permit_cannot_be_caller_boolean(tmp_path):
    m = leaf()
    for field, value in [
        ("symbol", "US.SPY"),
        ("input_window_digest", "f" * 64),
        ("approval_sha256", "f" * 64),
    ]:
        p = contract(m)
        p[field] = value
        with pytest.raises(m.CaptureRejected):
            m._validate_fixed_plan(p)


class Proto:
    def __init__(self, tree):
        self.tree = tree

    def IsInitialized(self):
        return True

    def SerializeToString(self, deterministic=False):
        assert deterministic
        return json.dumps(self.tree, sort_keys=True, separators=(",", ":")).encode()

    def ListFields(self):
        pairs = []
        for key, value in self.tree.items():
            repeated = type(value) is list
            if type(value) is dict:
                value = Proto(value)
            if repeated:
                value = [Proto(x) if type(x) is dict else x for x in value]
            pairs.append(
                (SimpleNamespace(name=key, is_repeated=repeated, label=3 if repeated else 1), value)
            )
        return pairs


def fake_sdk_modules(m, clock, root, *, autopage=False):
    import struct

    holder = SimpleNamespace(sent=[], connects=0, ctx=None)
    util = SimpleNamespace(
        MESSAGE_HEAD_FMT="<II",
        parse_head=lambda b: dict(zip(("proto_id", "serial_no"), struct.unpack("<II", b))),
        merge_qot_mkt_stock_str=lambda market, code: ("US." + code) if market == 11 else "WRONG",
    )
    constants = SimpleNamespace(ContextStatus=SimpleNamespace(READY="READY", CLOSED="CLOSED"))
    query_names = {
        "state": "GlobalStateQuery",
        "quota": "HistoryKLQuota",
        "basic": "StockBasicInfoQuery",
        "rehab": "RequestRehab",
        "dividends": "GetCorporateActionsDividendsQuery",
        "splits": "GetCorporateActionsStockSplitsQuery",
        "history": "RequestHistoryKlineQuery",
    }
    serial = [1]
    queries = {}
    for tag, name in query_names.items():

        def pack(cls, _tag=tag, **kwargs):
            serial[0] += 1
            return 0, "", struct.pack("<II", m.RPCS[_tag], serial[0]), m.RPCS[_tag], serial[0]

        queries[tag] = type(name, (), {"pack_req": classmethod(pack)})
    data = ScriptedBackend(m, None, None, clock, root)

    class Thread:
        def is_alive(self):
            return False

        def join(self, timeout=None):
            pass

    class Net:
        def __init__(self):
            self._conn_map = {7: object()}

        def connect(self, addr, handler, timeout, is_encrypt, is_sync=False):
            holder.connects += 1
            assert addr == ("127.0.0.1", 11112)
            return 0, None

        def send(self, conn, raw):
            holder.sent.append(struct.unpack("<II", raw))
            return 0, ""

        def _get_conn(self, conn):
            return self._conn_map.get(conn)

    class Context:
        def __init__(self, host, port, is_encrypt, is_async_connect=False, security_firm=None):
            self._net_mgr = Net()
            self._conn_id = 7
            self._auto_reconnect = True
            self._callback_executor = SimpleNamespace(_thread=Thread())
            self.status = "START"
            holder.ctx = self
            assert self._init_connect_sync() == 0

        def _init_connect_sync(self):
            assert self._auto_reconnect is False, "initial retry guard was installed too late"
            self._net_mgr.connect(("127.0.0.1", 11112), self, 20, False, is_sync=True)
            self._net_mgr.send(7, struct.pack("<II", 1001, 1))
            self.status = "READY"
            return 0

        def set_sync_query_connect_timeout(self, n):
            assert n == 5

        def _get_sync_query_processor(self, pack, unpack):
            def execute(**params):
                ret, msg, raw, proto, sn = pack(**params)
                self._net_mgr.send(7, raw)
                tag = next(k for k, v in m.RPCS.items() if v == proto)
                tree = data.trees.get(tag, {"retType": 0})
                return unpack(Proto(tree))

            return execute

        def query(self, tag, params, result):
            def unpack(pb):
                return 0, "", result

            ret, msg, value = self._get_sync_query_processor(queries[tag].pack_req, unpack)(
                **params
            )
            return ret, value

        def get_global_state(self):
            return self.query(
                "state",
                {},
                dict(
                    qot_logined=True,
                    server_ver="10.10.7008",
                    timestamp=str(clock.wall().timestamp()),
                ),
            )

        def get_history_kl_quota(self, get_detail=False):
            return self.query("quota", dict(get_detail=get_detail), (0, 5, []))

        def get_stock_basicinfo(self, market, stock_type, code_list):
            table = SimpleNamespace(
                to_dict=lambda orient: [
                    dict(code="US.IVV", stock_type="ETF", lot_size=1, exchange_type="FIXTURE")
                ]
            )
            return self.query(
                "basic", dict(market=market, stock_type=stock_type, code_list=code_list), table
            )

        def get_rehab(self, code):
            return self.query("rehab", dict(stock=code), None)

        def get_corporate_actions_dividends(self, code):
            return self.query("dividends", dict(code=code), None)

        def get_corporate_actions_stock_splits(self, code, next_key=None, num=None):
            return self.query("splits", dict(code=code, next_key=next_key, num=num), None)

        def request_history_kline(self, code, **kw):
            params = dict(
                code=code,
                start_date=kw["start"] + " 00:00:00",
                end_date=kw["end"] + " 23:59:59",
                ktype=kw["ktype"],
                autype=kw["autype"],
                fields=kw["fields"],
                max_num=kw["max_count"],
                next_req_key=kw["page_req_key"],
                extended_time=kw["extended_time"],
                session=kw["session"],
            )
            ret, value = self.query("history", params, None)
            if autopage:
                self.query("history", params, None)
            return ret, value, None

        def close(self):
            self.status = "CLOSED"
            self._net_mgr._conn_map.pop(7, None)

    sdk = SimpleNamespace(
        OpenQuoteContext=Context,
        SecurityFirm=SimpleNamespace(NONE="N/A"),
        Market=SimpleNamespace(US="US"),
        SecurityType=SimpleNamespace(ETF="ETF"),
        KLType=SimpleNamespace(K_DAY="K_DAY"),
        AuType=SimpleNamespace(NONE="None"),
        Session=SimpleNamespace(RTH="RTH"),
        KL_FIELD=SimpleNamespace(
            DATE_TIME="1", OPEN="2", HIGH="4", LOW="5", CLOSE="3", TRADE_VOL="8"
        ),
    )
    return (sdk, util, constants), holder


@pytest.mark.parametrize("autopage", [False, True])
def test_official_public_method_private_wrappers_are_scripted_not_live(tmp_path, autopage):
    m = leaf()
    assert hasattr(m, "_OfficialBackend"), "guarded official SDK backend is missing"
    root = tmp_path / "OWNED_SYNTHETIC"
    clock = Clock()
    modules, holder = fake_sdk_modules(m, clock, root, autopage=autopage)

    def factory(o, w, p, c):
        return m._OfficialBackend(o, w, p, c, modules=modules)

    result = m._run_capture(
        contract(m),
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=lambda p: None,
        synthetic=True,
        dates=DATES,
    )
    assert holder.connects == 1
    assert sum(proto == 3103 for proto, sn in holder.sent) == 1
    assert result["counts"]["application_sends"] == 7
    assert result["state"] == (
        "FAILED_CAPTURE_REQUIRES_PARENT_SEAL" if autopage else "CAPTURED_UNREVIEWED"
    )
    assert result["normal_close"]["callbacks_stopped"] is True
    assert "moomoo" not in sys.modules


def test_native_resource_values_must_be_actual_bounded_controls():
    m = leaf()
    assert hasattr(m, "_check_limits"), "native resource validator is missing"
    good = {
        "memory.max": "536870912",
        "memory.swap.max": "0",
        "pids.max": "32",
        "cpu.max": "50000 100000",
    }
    m._check_limits(good)
    for key, value in [
        ("memory.max", "max"),
        ("memory.swap.max", "max"),
        ("pids.max", "33"),
        ("cpu.max", "max 100000"),
    ]:
        bad = dict(good)
        bad[key] = value
        with pytest.raises(m.CaptureRejected):
            m._check_limits(bad)


def test_root_permit_duplicate_json_and_nonfinite_values_are_rejected():
    m = leaf()
    assert hasattr(m, "_strict_json"), "Root strict JSON parser is missing"
    for raw in (b'{"a":1,"a":2}', b'{"a":NaN}', b'{"a":Infinity}'):
        with pytest.raises(m.CaptureRejected):
            m._strict_json(raw)


def test_late_background_poison_during_close_never_returns_capture_success(tmp_path):
    m = leaf()
    clock = Clock()
    root = tmp_path / "OWNED_SYNTHETIC"

    def factory(o, w, p, c):
        b = ScriptedBackend(m, o, w, c, root)

        def close():
            b.closed = True
            try:
                o.reject("unexpected_background_send")
            except m.CaptureRejected:
                pass

        b.close = close
        return b

    result = m._run_capture(
        contract(m),
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=lambda p: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["state"].startswith("FAILED")


def test_native_phase_walls_include_factory_each_rpc_and_close(tmp_path):
    m = leaf()
    root = tmp_path / "OWNED_SYNTHETIC"

    class Phased(Clock):
        def __init__(self):
            super().__init__()
            self.phases = []

        def phase(self, until):
            import contextlib

            self.phases.append(until)
            return contextlib.nullcontext()

    clock = Phased()

    def factory(o, w, p, c):
        return ScriptedBackend(m, o, w, c, root)

    result = m._run_capture(
        contract(m),
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=lambda p: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["state"] == "CAPTURED_UNREVIEWED"
    assert 180 in clock.phases and len(clock.phases) >= 9 and max(clock.phases) <= 390


def test_successful_context_manifest_has_released_actor_and_effect_binding(tmp_path):
    m = leaf()
    root = tmp_path / "OWNED_SYNTHETIC"
    clock = Clock()
    plan = contract(m)
    binding = {
        "actor": {
            "pid": 123,
            "uid": 999,
            "start_ticks": 456,
            "cgroup": "/system.slice/OWNED_SYNTHETIC",
        },
        "root_go_sha256": "f" * 64,
        "catalog_sha256": "b" * 64,
        "capture_helper_sha256": "a" * 64,
    }
    plan["_verified_binding"] = binding

    def factory(o, w, p, c):
        return ScriptedBackend(m, o, w, c, root)

    result = m._run_capture(
        plan,
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=lambda p: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["source_binding"] == binding
    assert result["requires_parent_close_receipt"] is True


def test_positional_root_permit_read_keeps_caller_offset_and_descriptor(tmp_path, monkeypatch):
    import os
    import stat

    m = leaf()
    raw = b'{"schema_id":"OWNED_SYNTHETIC"}'
    p = tmp_path / "control.json"
    p.write_bytes(raw)
    fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    os.lseek(fd, 5, 0)
    original = os.fstat
    actual = original(fd)
    stamp = SimpleNamespace(
        st_dev=actual.st_dev,
        st_ino=actual.st_ino,
        st_size=len(raw),
        st_mtime_ns=actual.st_mtime_ns,
        st_ctime_ns=actual.st_ctime_ns,
        st_uid=0,
        st_nlink=1,
        st_mode=stat.S_IFREG | 0o444,
    )
    monkeypatch.setattr(m.os, "O_ACCMODE", 3, raising=False)
    monkeypatch.setitem(
        sys.modules, "fcntl", SimpleNamespace(F_GETFL=3, fcntl=lambda f, k: os.O_RDONLY)
    )
    monkeypatch.setattr(m.os, "fstat", lambda f: stamp if f == fd else original(f))
    monkeypatch.setattr(m.os, "pread", lambda f, n, o: raw[o : o + n], raising=False)
    try:
        result = m._read_held_json(fd, hashlib.sha256(raw).hexdigest())
        assert result["schema_id"] == "OWNED_SYNTHETIC"
        assert os.lseek(fd, 0, 1) == 5 and original(fd).st_size == len(raw)
        with pytest.raises(m.CaptureRejected):
            m._read_held_json(fd, "f" * 64)
        stamp.st_nlink = 2
        with pytest.raises(m.CaptureRejected):
            m._read_held_json(fd, hashlib.sha256(raw).hexdigest())
    finally:
        os.close(fd)


def test_nested_native_alarm_clamps_to_outer_and_restores_only_owned_timer(monkeypatch):
    m = leaf()
    events = []
    state = {"handler": "ORIGINAL", "timer": 0.0}
    fake = SimpleNamespace(
        SIGALRM=14,
        ITIMER_REAL=0,
        getsignal=lambda n: state["handler"],
        getitimer=lambda n: (state["timer"], 0.0),
    )

    def signal(n, h):
        state["handler"] = h

    def timer(n, v):
        state["timer"] = v
        events.append(v)

    fake.signal = signal
    fake.setitimer = timer
    monkeypatch.setattr(m, "signal", fake)
    clock = m._NativeClock()
    clock.mono = lambda: 0.0
    with clock.phase(480):
        with clock.phase(20):
            assert state["timer"] == 20
        assert state["timer"] == 480
    assert state == {"handler": "ORIGINAL", "timer": 0}
    state["timer"] = 5
    with pytest.raises(m.CaptureRejected):
        with clock.phase(480):
            pass


def test_caller_cannot_add_unapproved_plan_fields():
    m = leaf()
    plan = contract(m)
    plan["provider_permission_verified"] = True
    with pytest.raises(m.CaptureRejected, match="unknown_plan"):
        m._validate_production_plan_keys(plan)


def test_official_history_wire_dates_are_full_day_timestamps():
    m = leaf()
    assert m.PARAMS["history"]["start_date"] == "2026-05-08 00:00:00"
    assert m.PARAMS["history"]["end_date"] == "2026-10-29 23:59:59"


def test_normalizer_preserves_large_integral_volume():
    m = leaf()
    data = originals()
    data["history_pages"][0]["rows"][0]["raw"]["volume"] = 2**53 + 1
    result = m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))
    assert result["bars"][0]["volume"] == 2**53 + 1


def test_cash_sum_must_remain_finite_in_output():
    m = leaf()
    data = originals()
    day = DATES[3]
    data["adjustment_factors"]["rows"] = [
        row(time=day, companyActFlag=192, dividend=1e308, spDividend=1e308)
    ]
    data["dividends"]["rows"] = [
        row(exDate=day, dividendPayableDate=DATES[5], statement="USD " + "2" + "0" * 308)
    ]
    with pytest.raises(m.CaptureRejected):
        m.normalize_capture(data, schedule=SCHEDULE, source_facts=facts(m, data))


def test_unknown_nonempty_cash_lexeme_is_retained_for_closed_input_review():
    m = leaf()
    data = ScriptedBackend(m, None, None, Clock(), Path("UNUSED"))
    data.trees.pop("history")
    data.trees["dividends"]["s2c"]["dividendList"][0]["statement"] = (
        "Unrecognized locale cash statement"
    )
    observer = SimpleNamespace(trees=data.trees, responses={})
    m._precheck_actions(observer, DATES)
    plain = m._plain_from_originals(observer)
    assert plain["dividends"]["rows"][0]["raw"]["statement"] == "Unrecognized locale cash statement"


@pytest.mark.parametrize("statement", ["", None, "USD 1.50 per share"])
def test_missing_or_known_conflicting_cash_statement_stops_before_price(statement):
    m = leaf()
    data = ScriptedBackend(m, None, None, Clock(), Path("UNUSED"))
    data.trees.pop("history")
    data.trees["dividends"]["s2c"]["dividendList"][0]["statement"] = statement
    with pytest.raises(m.CaptureRejected):
        m._precheck_actions(SimpleNamespace(trees=data.trees, responses={}), DATES)


def test_initial_control_cannot_be_sent_twice(tmp_path):
    m = leaf()
    o = m._CaptureObserver(contract(m), None, Clock())
    o.before_send(1001, 1)
    with pytest.raises(m.CaptureRejected):
        o.before_send(1001, 2)


def test_provider_bounds_require_real_identity_and_evidence_refs():
    m = leaf()
    plan = contract(m)
    bounds = {
        "schema_id": "qm.ivv.provider-bounds.v1",
        "state": "COMPLETED_EXISTING_BOUNDS",
        "effect_id": plan["effect_id"],
        "max_incremental_bytes": 32 * m.MIB,
        "valid_until_monotonic": 480,
    }
    assert hasattr(m, "_validate_provider_bounds"), (
        "provider control claims need identity/evidence validation"
    )
    with pytest.raises(m.CaptureRejected):
        m._validate_provider_bounds(bounds, plan)
    bounds.update(
        provider_actor={
            "pid": 42,
            "uid": 1000,
            "start_ticks": 123,
            "exe_sha256": "d" * 64,
            "machine_identity_sha256": "e" * 64,
        },
        evidence_refs=[{"path": "/root/controls/original-bound.json", "sha256": "f" * 64}],
    )
    assert m._validate_provider_bounds(bounds, plan) == bounds["evidence_refs"]


@pytest.mark.parametrize("statement", ["EUR 1.25 per share", "HKD 1.25 per share"])
def test_explicit_foreign_currency_prevents_history_send(tmp_path, statement):
    m = leaf()
    root = tmp_path / "OWNED_SYNTHETIC"
    clock = Clock()

    def factory(o, w, p, c):
        backend = ScriptedBackend(m, o, w, c, root)
        backend.trees["dividends"]["s2c"]["dividendList"][0]["statement"] = statement
        return backend

    result = m._run_capture(
        contract(m),
        root,
        backend_factory=factory,
        clock=clock,
        sync_dir=lambda p: None,
        synthetic=True,
        dates=DATES,
    )
    assert result["state"] == "FAILED_CAPTURE_REQUIRES_PARENT_SEAL"
    assert result["counts"]["history_sends"] == 0
    assert result["counts"]["application_sends"] == 6
    assert result["normal_close"] == {
        "context_closed": True,
        "callbacks_stopped": True,
        "data_socket_closed": True,
    }
    plain = json.loads((root / result["plain_ref"]["path"]).read_bytes())
    assert plain["dividends"]["rows"][0]["raw"]["statement"] == statement
    assert "moomoo" not in sys.modules


@pytest.mark.parametrize(
    "statement", ["EUR 1.25", "EUR1.25", "HK$1.25", "€1.25", "CAD 1.25", "每股派息1.25港元"]
)
def test_recognized_non_usd_cash_is_a_known_contradiction(statement):
    m = leaf()
    data = ScriptedBackend(m, None, None, Clock(), Path("UNUSED"))
    data.trees.pop("history")
    data.trees["dividends"]["s2c"]["dividendList"][0]["statement"] = statement
    with pytest.raises(m.CaptureRejected, match="cash_currency_conflict"):
        m._precheck_actions(SimpleNamespace(trees=data.trees, responses={}), DATES)


@pytest.mark.parametrize(
    "statement",
    ["USD 1.25 per share", "US$ 1.25 per share", "每股派息1.25美元", "1.25 USD per share"],
)
def test_supported_usd_lexemes_are_not_foreign_currency(statement):
    m = leaf()
    data = ScriptedBackend(m, None, None, Clock(), Path("UNUSED"))
    data.trees.pop("history")
    data.trees["dividends"]["s2c"]["dividendList"][0]["statement"] = statement
    m._precheck_actions(SimpleNamespace(trees=data.trees, responses={}), DATES)
