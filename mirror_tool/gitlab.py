import logging
from typing import Any, Dict

import jinja2
import requests

from .conf import GitlabMerge
from .git_info import UpdateInfo
from .jinja import jinja_args

LOG = logging.getLogger("mirror-tool")
SHARED_LABEL = "mirror-tool"


class GitlabException(RuntimeError):
    pass


class GitlabSession:
    def __init__(self, gitlab_merge: GitlabMerge, run_cmd, updates: list[UpdateInfo]):
        for field in ("api_v4_url", "project_id", "push_url"):
            if not getattr(gitlab_merge, field):
                raise GitlabException(
                    (
                        f"Cannot create GitLab MR: required config '{field}' is not set and "
                        "can't be determined automatically. Please run the tool within a GitLab pipeline "
                        "or set this field in the mirror-tool configuration file."
                    )
                )

        self.gitlab_merge = gitlab_merge
        self.api_v4_url = gitlab_merge.api_v4_url
        self.project_id = gitlab_merge.project_id
        self.requests = requests.Session()
        self.requests.headers["PRIVATE-TOKEN"] = self.gitlab_merge.token_final

        self.run_cmd = run_cmd

        jinja_loader = jinja2.DictLoader(
            {
                "title": self.gitlab_merge.title,
                "description": self.gitlab_merge.description,
                "comment.create": self.gitlab_merge.comment.create,
                "comment.update": self.gitlab_merge.comment.update,
            }
        )
        self.updates = updates
        self.jinja_env = jinja2.Environment(loader=jinja_loader)
        self.jinja_args = jinja_args(updates=self.updates)

    def jinja_render(self, template_name, *args, **kwargs):
        kwargs.update(self.jinja_args)
        return self.jinja_env.get_template(template_name).render(*args, **kwargs)

    @property
    def project_mrs_url(self):
        return "".join(
            [self.api_v4_url, "/projects/", str(self.project_id), "/merge_requests"]
        )

    def raise_bad_response(self, doing_what, response):
        LOG.warning(
            "Unexpected response from GitLab: %s %s",
            response.status_code,
            response.reason,
        )
        LOG.warning("Response body: %s", response.json())
        raise GitlabException(f"Failed to {doing_what}")

    def ensure_pushed_to_src(self, revision):
        try:
            self.run_cmd(
                [
                    "git",
                    "push",
                    self.gitlab_merge.push_url_final,
                    f"+{revision}:refs/heads/{self.gitlab_merge.src}",
                ],
                silent=True,
            )
        except Exception:
            # The unusual error handling here is because the push_url is
            # likely to contain a token which shouldn't be leaked, and the exception
            # is going to contain the command by default. So we drop that and raise
            # our own more vague exception.
            LOG.debug("Command failed", exc_info=True)
            raise GitlabException(f"Could not push to {self.gitlab_merge.src} branch.")

    def mutable_mr_attributes(self) -> Dict[str, Any]:
        return dict(
            title=self.jinja_render("title"),
            allow_collaboration=True,
            squash=False,
            labels=[SHARED_LABEL] + self.gitlab_merge.labels,
            description=self.jinja_render("description"),
        )

    def create_mr(self) -> bool:
        # https://docs.gitlab.com/ee/api/merge_requests.html#create-mr
        LOG.info("Creating GitLab merge request ...")

        create_attrs = self.mutable_mr_attributes()
        create_attrs["source_branch"] = self.gitlab_merge.src
        create_attrs["target_branch"] = self.gitlab_merge.dest

        response = self.requests.post(
            self.project_mrs_url,
            json=create_attrs,
        )

        LOG.info("GitLab response: %s", response.status_code)

        if response.ok:
            body = response.json()
            LOG.info(
                "Created: %s", body.get("web_url") or "<unknown merge request URL>"
            )
            self.add_comment(body, self.jinja_render("comment.create"))
            return True

        elif response.status_code == 409:
            return False

        self.raise_bad_response("create merge request", response)

    def update_mr(self, mr) -> None:
        url = "".join([self.project_mrs_url, "/", str(mr["iid"])])

        update_attrs = self.mutable_mr_attributes()

        response = self.requests.put(url, json=update_attrs)

        if not response.ok:
            self.raise_bad_response("update merge request", response)

        self.add_comment(mr, self.jinja_render("comment.update"))

        LOG.info("Updated: %s", mr.get("web_url") or "<unknown merge request URL>")

    def add_comment(self, mr, body):
        if not body:
            return

        # https://docs.gitlab.com/ee/api/notes.html#create-new-merge-request-note
        iid = mr["iid"]
        url = "".join([self.project_mrs_url, "/", str(iid), "/notes"])

        response = self.requests.post(url, json=dict(body=body))
        if not response.ok:
            self.raise_bad_response("add comment", response)

        LOG.info("Commented on: %s", mr.get("web_url") or "<unknown merge request URL>")

    def find_mr(self) -> dict:
        response = self.requests.get(
            self.project_mrs_url,
            params={
                "state": "opened",
                "source_branch": self.gitlab_merge.src,
                "target_branch": self.gitlab_merge.dest,
            },
        )

        if not response.ok:
            self.raise_bad_response("find merge request", response)

        mrs = response.json()
        for mr in mrs:
            LOG.info(
                "Found existing merge request: %s",
                mr.get("web_url") or "<unknown url>",
            )

            if SHARED_LABEL in (mr.get("labels") or []):
                return mr

            # If we get here, that means we found an MR for the right
            # branches but it apparently wasn't created by us?
            # That makes it not safe to proceed.
            raise GitlabException(
                "An existing merge request was found, but it was apparently "
                "not created by mirror-tool! Refusing to update. Please close the MR manually "
                "(if it is safe to do so), then re-run the tool."
            )

        # If we get here, that means we didn't find any MR at all which
        # is unexpected.
        raise GitlabException(
            "Failed to create MR due to conflict, "
            "but also failed to locate an existing MR!"
        )

    def ensure_merge_request_exists(self, revision="HEAD"):
        # First have to make sure it's pushed.
        self.ensure_pushed_to_src(revision)

        # Create if it didn't already exist.
        if self.create_mr():
            return

        LOG.info("GitLab merge request seems to already exist, searching...")
        mr = self.find_mr()
        self.update_mr(mr)
