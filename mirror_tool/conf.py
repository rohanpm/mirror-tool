from dataclasses import dataclass
from typing import List

import jsonschema

from ruamel.yaml import YAML

CONFIG_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "definitions": {
        "relativeDir": {
            "allOf": [
                {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 4000,
                },
                {"not": {"type": "string", "pattern": r"\.\."}},
                {"not": {"type": "string", "pattern": r"//"}},
                {"not": {"type": "string", "pattern": r"^/"}},
            ],
        },
        "mirror": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 4000,
                },
                "ref": {
                    "type": "string",
                    "minLength": 2,
                    "maxLength": 4000,
                },
                "dir": {"$ref": "#/definitions/relativeDir"},
            },
            "required": ["url", "ref"],
            "additionalProperties": False,
        },
        "mirrorList": {
            "type": "array",
            "items": {"$ref": "#/definitions/mirror"},
        },
    },
    "type": "object",
    "properties": {
        "mirror": {"$ref": "#/definitions/mirrorList"},
    },
    "required": [],
    "additionalProperties": False,
}


@dataclass
class Mirror:
    url: str
    ref: str
    dir: str = "upstream"


class Config:
    def __init__(self, raw):
        self._raw = raw

    @property
    def mirrors(self) -> List[Mirror]:
        out = []
        for elem in self._raw.get("mirror") or []:
            out.append(Mirror(**elem))
        return out

    def validate(self) -> None:
        jsonschema.validate(self._raw, CONFIG_SCHEMA)

    @classmethod
    def from_file(cls, filename=".mirror-tool.yaml") -> "Config":
        with open(filename, "rt") as f:
            raw = YAML(typ="safe").load(f)
        return cls(raw)
