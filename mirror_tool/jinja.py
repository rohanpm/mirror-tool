import datetime
import os
from typing import Any


def jinja_args(**kwargs) -> dict[str, Any]:
    now = datetime.datetime.utcnow()
    out = dict(
        env=os.environ,
        datetime_iso8601=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        datetime_minute=now.strftime("%Y-%m-%d %H:%M"),
        datetime_day=now.strftime("%Y-%m-%d"),
        datetime_week=now.strftime("%Ywk%U"),
    )
    out.update(kwargs)
    return out
