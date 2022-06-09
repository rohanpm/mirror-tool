import datetime
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List

import jsonschema
from ruamel.yaml import YAML

from .git_info import Commit, UpdateInfo
from .jinja import jinja_validate
from .shared import Mirror

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
        },
    },
    "type": "object",
    "properties": {
        "mirror": {"$ref": "#/definitions/mirrorList"},
        "gitlab_merge": {"$ref": "#/definitions/gitlabMerge"},
        "gitlab_promote": {
            "type": "array",
            # TODO: actually it's not 100% identical to gitlabMerge.
            "items": {"$ref": "#/definitions/gitlabMerge"},
        },
        "git_config": {"type": "object"},
        "commitmsg": {
            "type": "string",
            "minLength": 1,
            "maxLength": 8000,
        },
    },
    "required": [],
    "additionalProperties": False,
}


@dataclass
class GitlabMergeComments:
    create: str = ""
    update: str = ""


@dataclass
class GitlabCommon:
    src: str = "latest"
    dest: str = "main"
    title: str = "Update mirror"

    # This MUST be '$ENV_VAR_NAME'
    token: str = "$GITLAB_MIRROR_TOKEN"

    labels: List[str] = field(default_factory=list)
    description: str = "Automated update of dependencies."
    comment: GitlabMergeComments = GitlabMergeComments()

    # The defaults here assume that we are running from a gitlab CI pipeline.
    # Predefined vars are documented at:
    # https://docs.gitlab.com/ee/ci/variables/predefined_variables.html
    api_v4_url: str = field(default_factory=lambda: os.environ.get("CI_API_V4_URL"))
    project_id: int = field(
        default_factory=lambda: int(os.environ.get("CI_PROJECT_ID") or "0")
    )

    push_url: str = field(
        default_factory=lambda: os.environ.get("CI_PROJECT_URL") or ""
    )

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
class GitlabMerge(GitlabCommon):
    enabled: bool = False


@dataclass
class GitlabPromote(GitlabCommon):
    title: str = "Promote changes"
    description: str = "Automated promotion between branches."

    @property
    def working_branch(self) -> str:
        return f"mirror-tool/promote-{self.src}-to-{self.dest}"


# Objects used for jinja validation purposes.
VALIDATE_COMMIT = Commit(
    revision="55810cd62082f26ec39a9df332af1aa9db6e6b91",
    revision_abbrev="55810cd",
    author_name="Rohan McGovern",
    author_email="rohan@mcgovern.id.au",
    author_email_local="rohan",
    author_datetime=datetime.datetime(2022, 6, 6, 22, 33, 34),
    committer_name="GitHub",
    committer_email="noreply@github.com",
    committer_email_local="noreply",
    committer_datetime=datetime.datetime(2022, 6, 6, 22, 33, 34),
    subject="Merge pull request #33 from rohanpm/empty-log",
    body="Fix a crash when commit log has an empty entry",
)

VALIDATE_MIRROR = Mirror(
    url="https://example.com/foo",
    ref="refs/heads/quux",
)

VALIDATE_UPDATEINFO = UpdateInfo(
    mirror=VALIDATE_MIRROR, commits=[VALIDATE_COMMIT], commit_count=1, changed=True
)

# This is straight from https://docs.gitlab.com/ee/api/merge_requests.html#get-single-mr
VALIDATE_MERGEREQUEST = {
    "id": 155016530,
    "iid": 133,
    "project_id": 15513260,
    "title": "Manual job rules",
    "description": "",
    "state": "opened",
    "created_at": "2022-05-13T07:26:38.402Z",
    "updated_at": "2022-05-14T03:38:31.354Z",
    "merge_user": None,
    "merged_at": None,
    "closed_by": None,
    "closed_at": None,
    "target_branch": "master",
    "source_branch": "manual-job-rules",
    "user_notes_count": 0,
    "upvotes": 0,
    "downvotes": 0,
    "author": {
        "id": 4155490,
        "username": "marcel.amirault",
        "name": "Marcel Amirault",
        "state": "active",
        "avatar_url": "https://gitlab.com/uploads/-/system/user/avatar/4155490/avatar.png",
        "web_url": "https://gitlab.com/marcel.amirault",
    },
    "assignees": [],
    "assignee": None,
    "reviewers": [],
    "source_project_id": 15513260,
    "target_project_id": 15513260,
    "labels": [],
    "draft": False,
    "work_in_progress": False,
    "milestone": None,
    "merge_when_pipeline_succeeds": False,
    "merge_status": "can_be_merged",
    "sha": "e82eb4a098e32c796079ca3915e07487fc4db24c",
    "merge_commit_sha": None,
    "squash_commit_sha": None,
    "discussion_locked": None,
    "should_remove_source_branch": None,
    "force_remove_source_branch": True,
    "reference": "!133",
    "references": {
        "short": "!133",
        "relative": "!133",
        "full": "marcel.amirault/test-project!133",
    },
    "web_url": "https://gitlab.com/marcel.amirault/test-project/-/merge_requests/133",
    "time_stats": {
        "time_estimate": 0,
        "total_time_spent": 0,
        "human_time_estimate": None,
        "human_total_time_spent": None,
    },
    "squash": False,
    "task_completion_status": {"count": 0, "completed_count": 0},
    "has_conflicts": False,
    "blocking_discussions_resolved": True,
    "approvals_before_merge": None,
    "subscribed": True,
    "changes_count": "1",
    "latest_build_started_at": "2022-05-13T09:46:50.032Z",
    "latest_build_finished_at": None,
    "first_deployed_to_production_at": None,
    "head_pipeline": {
        "id": 538317940,
        "iid": 1877,
        "project_id": 15513260,
        "sha": "1604b0c46c395822e4e9478777f8e54ac99fe5b9",
        "ref": "refs/merge-requests/133/merge",
        "status": "failed",
        "source": "merge_request_event",
        "created_at": "2022-05-13T09:46:39.560Z",
        "updated_at": "2022-05-13T09:47:20.706Z",
        "web_url": "https://gitlab.com/marcel.amirault/test-project/-/pipelines/538317940",
        "before_sha": "1604b0c46c395822e4e9478777f8e54ac99fe5b9",
        "tag": False,
        "yaml_errors": None,
        "user": {
            "id": 4155490,
            "username": "marcel.amirault",
            "name": "Marcel Amirault",
            "state": "active",
            "avatar_url": "https://gitlab.com/uploads/-/system/user/avatar/4155490/avatar.png",
            "web_url": "https://gitlab.com/marcel.amirault",
        },
        "started_at": "2022-05-13T09:46:50.032Z",
        "finished_at": "2022-05-13T09:47:20.697Z",
        "committed_at": None,
        "duration": 30,
        "queued_duration": 10,
        "coverage": None,
        "detailed_status": {
            "icon": "status_failed",
            "text": "failed",
            "label": "failed",
            "group": "failed",
            "tooltip": "failed",
            "has_details": True,
            "details_path": "/marcel.amirault/test-project/-/pipelines/538317940",
            "illustration": None,
            "favicon": "/assets/ci_favicons/favicon_status_failed-41304d7f7e3828808b0c26771f0309e55296819a9beea3ea9fbf6689d9857c12.png",
        },
    },
    "diff_refs": {
        "base_sha": "1162f719d711319a2efb2a35566f3bfdadee8bab",
        "head_sha": "e82eb4a098e32c796079ca3915e07487fc4db24c",
        "start_sha": "1162f719d711319a2efb2a35566f3bfdadee8bab",
    },
    "merge_error": None,
    "first_contribution": False,
    "user": {"can_merge": True},
}


class Config:
    def __init__(self, raw):
        self._raw = raw

    @property
    def gitlab_merge(self) -> GitlabMerge:
        raw = (self._raw.get("gitlab_merge") or {}).copy()
        raw_comment = raw.get("comment") or {}
        raw["comment"] = GitlabMergeComments(**raw_comment)
        return GitlabMerge(**raw)

    @property
    def gitlab_promote(self) -> List[GitlabPromote]:
        out = []
        raw = self._raw.get("gitlab_promote") or []
        for elem in raw:
            elem = elem.copy()
            raw_comment = elem.get("comment") or {}
            elem["comment"] = GitlabMergeComments(**raw_comment)
            out.append(GitlabPromote(**elem))
        return out

    @property
    def git_config(self) -> Dict[str, Any]:
        return self._raw.get("git_config") or {}

    @property
    def mirrors(self) -> List[Mirror]:
        out = []
        for elem in self._raw.get("mirror") or []:
            out.append(Mirror(**elem))
        return out

    @property
    def commitmsg(self) -> str:
        return (
            self._raw.get("commitmsg")
            or "merging {{mirror.dir}} at {{datetime_minute}}"
        )

    def validate(self) -> None:
        jsonschema.validate(self._raw, CONFIG_SCHEMA)

        mirror_dirs = {mirror.dir for mirror in self.mirrors}
        if len(mirror_dirs) != len(self.mirrors):
            raise jsonschema.ValidationError(
                message="Multiple mirrors defined using same dir",
                path=["mirror"],
                instance=self.mirrors,
            )

        self.jinja_validate_all()

    def jinja_validate_all(self):
        updates = [VALIDATE_UPDATEINFO, VALIDATE_UPDATEINFO]
        jinja_templates = []
        jinja_templates.append(
            (["commitmsg"], self.commitmsg, asdict(VALIDATE_UPDATEINFO))
        )

        def append_gitlab_common(base_path, instance, **kwargs):
            jinja_templates.append(
                (base_path + ["title"], getattr(instance, "title"), kwargs)
            )
            jinja_templates.append(
                (base_path + ["description"], getattr(instance, "description"), kwargs)
            )

            comment = getattr(instance, "comment")
            jinja_templates.append(
                (base_path + ["comment", "create"], comment.create, kwargs)
            )
            jinja_templates.append(
                (base_path + ["comment", "update"], comment.update, kwargs)
            )

        append_gitlab_common(["gitlab_merge"], self.gitlab_merge, updates=updates)

        for i, elem in enumerate(self.gitlab_promote):
            base_path = ["gitlab_promote", i]
            append_gitlab_common(base_path, elem, src_mr=VALIDATE_MERGEREQUEST)

        for (path, template, kwargs) in jinja_templates:
            self.jinja_validate(template, path, **kwargs)

    def jinja_validate(self, template, path, **kwargs):
        try:
            jinja_validate(template, **kwargs)
        except Exception as exc:
            raise jsonschema.ValidationError(
                message="Invalid Jinja template: %s" % str(exc),
                path=path,
                instance="<jinja template starting: %r...>" % (template[:50]),
                cause=exc,
            )

    @classmethod
    def from_file(cls, filename=".mirror-tool.yaml") -> "Config":
        with open(filename, "rt") as f:
            raw = YAML(typ="safe").load(f)
        return cls(raw)
