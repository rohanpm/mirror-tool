import datetime
import os
from typing import Any

import jinja2


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


def jinja_validate(template: str, **kwargs):
    loader = jinja2.DictLoader({"template": template})
    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    loader.load(env, "template").render(jinja_args(**kwargs))
