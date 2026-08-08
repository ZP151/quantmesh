"""Structured logging formatter (M10 Phase A, issue #58).

One JSON object per line — ts, level, logger, message, and an
optional ``fields`` dict carried on ``extra={"fields": {...}}``.
Serialization never raises: non-JSON-serializable field values fall
back to ``repr``, and the formatter itself cannot break a caller's
logging call.
"""

import json
import logging
from datetime import UTC, datetime


class StructuredFormatter(logging.Formatter):
    """Emit one JSON line per record::

        logger.info("reconciled", extra={"fields": {"deltas": 0}})
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "fields": getattr(record, "fields", None) or {},
        }
        return json.dumps(payload, sort_keys=True, default=repr, ensure_ascii=True)
