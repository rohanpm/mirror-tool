import os
from dataclasses import dataclass
from typing import List

import jsonschema

from ruamel.yaml import YAML

CONFIG_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "definitions": {
        "jinjaTemplateLarge": {"type": "string", "minLength": 0, "maxLength": 8000},
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
        "gitlabMerge": {
            "type": "object",
            "properties": {
                "enabled": {"type": "boolean"},
                "src": {"type": "string", "minLength": 1, "maxLength": 200},
                "dest": {"type": "string", "minLength": 1, "maxLength": 200},
                "title": {"type": "string", "minLength": 1, "maxLength": 2000},
                "description": {"type": "string", "minLength": 0, "maxLength": 8000},
                "token": {"type": "string", "pattern": r"^\$.+"},
                "labels": {
                    "type": "array",
                    "items": {"type": "string", "minLength": 1, "maxLength": 50},
                },
                "comment": {
                    "type": "object",
                    "properties": {
                        "create": {"$ref": "#/definitions/jinjaTemplateLarge"},
                        "update": {"$ref": "#/definitions/jinjaTemplateLarge"},
                    },
                    "additionalProperties": False,
                },
            },
            "additionalProperties": False,
        }
        # gitlab_merge:
        #   enabled: true
        #   src: latest
        #   dest: qa
        #   title: "Deploy to QA"
        #   token: $GITLAB_MIRROR_TOKEN
        #   labels:
        #   - deploy
        #   description: "implement me!"
        #   comment:
        #     create: "a comment added on creation"
        #     update: "a comment added on update"
    },
    "type": "object",
    "properties": {
        "mirror": {"$ref": "#/definitions/mirrorList"},
        "gitlab_merge": {"$ref": "#/definitions/gitlabMerge"},
    },
    "required": [],
    "additionalProperties": False,
}


@dataclass
class GitlabMerge:
    enabled: bool = False
    src: str = "latest"
    dest: str = ""
    title: str = "Update mirror"

    # This MUST be '$ENV_VAR_NAME'
    token: str = "$GITLAB_MIRROR_TOKEN"

    # The defaults here assume that we are running from a gitlab CI pipeline.
    # Predefined vars are documented at:
    # https://docs.gitlab.com/ee/ci/variables/predefined_variables.html
    api_v4_url: str = os.environ.get("CI_API_V4_URL")
    project_id: int = int(os.environ.get("CI_PROJECT_ID") or "0")

    push_url: str = os.environ.get("CI_PROJECT_URL") or ""
    # CI_PROJECT_URL=https://token:[TOKEN]@gitlab.cee.redhat.com/rmcgover/c3i-test

    # CI_PROJECT_ID=57572
    # CI_PROJECT_NAME=c3i-test
    # CI_PROJECT_NAMESPACE=rmcgover
    # CI_PROJECT_URL=https://gitlab.cee.redhat.com/rmcgover/c3i-test
    # CI_SERVER_URL=https://gitlab.cee.redhat.com

    @property
    def token_final(self) -> str:
        if not self.token.startswith("$"):
            raise ValueError(
                f"Invalid token: '{self.token}'. Must be of form '$ENV_VAR_NAME'."
            )
        key = self.token[1:]
        if key not in os.environ:
            raise ValueError(f"GitLab token not available in {self.token}.")

        return os.environ[key]

    @property
    def push_url_final(self) -> str:
        return self._token_auth(self.push_url)

    @property
    def api_v4_url_final(self) -> str:
        return self._token_auth(self.api_v4_url)

    def _token_auth(self, url: str):
        if not url.startswith("https://"):
            # Not using token-based auth
            return url
        if "@" in url:
            # Maybe the caller already set up auth in the URL
            return url

        url_noscheme = url[len("https://") :]
        return "".join(["https://", "token:", self.token_final, "@", url_noscheme])


@dataclass
class Mirror:
    url: str
    ref: str
    dir: str = "upstream"


class Config:
    def __init__(self, raw):
        self._raw = raw

    @property
    def gitlab_merge(self) -> GitlabMerge:
        raw = self._raw.get("gitlab_merge") or {}
        return GitlabMerge(**raw)

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
