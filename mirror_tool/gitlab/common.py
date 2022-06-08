import logging
import subprocess
from typing import Any, Callable, Dict, List, Tuple

import jinja2
import requests

from ..conf import GitlabCommon

LOG = logging.getLogger("mirror-tool")
SHARED_LABEL = "mirror-tool"

RunCmd = Callable[..., subprocess.CompletedProcess]


class GitlabException(RuntimeError):
    pass


class GitlabSession:
    def __init__(self, gitlab_info: GitlabCommon, run_cmd: RunCmd):
        for field in ("api_v4_url", "project_id", "push_url"):
            if not getattr(gitlab_info, field):
                raise GitlabException(
                    (
                        f"Cannot connect to GitLab: required config '{field}' is not set and "
                        "can't be determined automatically. Please run the tool within a GitLab pipeline "
                        "or set this field in the mirror-tool configuration file."
                    )
                )

        self.gitlab_info = gitlab_info
        self.api_v4_url = gitlab_info.api_v4_url
        self.project_id = gitlab_info.project_id
        self.requests = requests.Session()
        self.requests.headers["PRIVATE-TOKEN"] = gitlab_info.token_final

        self.run_cmd = run_cmd

        jinja_loader = jinja2.DictLoader(
            {
                "title": self.gitlab_info.title,
                "description": self.gitlab_info.description,
                "comment.create": self.gitlab_info.comment.create,
                "comment.update": self.gitlab_info.comment.update,
            }
        )
        self.jinja_env = jinja2.Environment(loader=jinja_loader)
        self.jinja_args = {}

    def jinja_render(self, template_name, *args, **kwargs):
        kwargs.update(self.jinja_args)
        return self.jinja_env.get_template(template_name).render(*args, **kwargs)

    @property
    def project_mrs_url(self):
        return "".join(
            [self.api_v4_url, "/projects/", str(self.project_id), "/merge_requests"]
        )

    def response_ok(self, doing_what, response):
        if not response.ok:
            LOG.warning(
                "Unexpected response from GitLab: %s %s",
                response.status_code,
                response.reason,
            )
            LOG.warning("Response body: %s", response.json())
            raise GitlabException(f"Failed to {doing_what}")

    def run_git_silent(self, cmd, doing_what):
        try:
            self.run_cmd(cmd, silent=True)
        except Exception:
            # The unusual error handling here is because the push_url is
            # likely to contain a token which shouldn't be leaked, and the exception
            # is going to contain the command by default. So we drop that and raise
            # our own more vague exception.
            LOG.debug("Command failed", exc_info=True)
            raise GitlabException(f"Could not {doing_what}.")

    def ensure_pushed_to(self, revision, dest):
        self.run_git_silent(
            [
                "git",
                "push",
                self.gitlab_info.push_url_final,
                f"+{revision}:refs/heads/{dest}",
            ],
            f"push {revision} to {dest} branch",
        )

    def mutable_mr_attributes(self) -> Dict[str, Any]:
        return dict(
            title=self.jinja_render("title"),
            allow_collaboration=True,
            squash=False,
            labels=[SHARED_LABEL] + self.gitlab_info.labels,
            description=self.jinja_render("description"),
        )

    def create_mr_with_branches(self, src, dest) -> bool:
        """Make a merge request in the configured repo from 'src' to 'dest' branch.

        Returns True if MR created, False if MR not created due to conflict, or
        raises on error.
        """

        # https://docs.gitlab.com/ee/api/merge_requests.html#create-mr
        LOG.info("Creating GitLab merge request ...")

        create_attrs = self.mutable_mr_attributes()
        create_attrs["source_branch"] = src
        create_attrs["target_branch"] = dest

        response = self.requests.post(
            self.project_mrs_url,
            json=create_attrs,
        )

        LOG.info("GitLab response: %s", response.status_code)

        if response.status_code == 409:
            # This code is tolerated as meaning that an MR already exists.
            return False

        self.response_ok("create merge request", response)

        body = response.json()
        LOG.info("Created: %s", body.get("web_url") or "<unknown merge request URL>")
        self.add_comment(body, self.jinja_render("comment.create"))
        return True

    def update_mr(self, mr) -> None:
        url = "".join([self.project_mrs_url, "/", str(mr["iid"])])

        update_attrs = self.mutable_mr_attributes()

        response = self.requests.put(url, json=update_attrs)

        self.response_ok("update merge request", response)

        self.add_comment(mr, self.jinja_render("comment.update"))

        LOG.info("Updated: %s", mr.get("web_url") or "<unknown merge request URL>")

    def add_comment(self, mr, body):
        if not body:
            return

        # https://docs.gitlab.com/ee/api/notes.html#create-new-merge-request-note
        iid = mr["iid"]
        url = "".join([self.project_mrs_url, "/", str(iid), "/notes"])

        response = self.requests.post(url, json=dict(body=body))
        self.response_ok("add comment", response)

        LOG.info("Commented on: %s", mr.get("web_url") or "<unknown merge request URL>")

    def find_mrs_with_fields(self, fields) -> Tuple[dict, dict]:
        """Searches for MRs matching passed fields.

        Returns a tuple of:

          (list of matching MRs created by mirror-tool,
           list of all matching MRs)
        """

        # Note: for the time being, lack of pagination here should be OK.
        #
        # - default sort will return newest MRs first.
        # - default pagination is to return first page only.
        #
        # So, default behavior is to return ~20 most recent MRs only.
        # It should be OK for the purpose of this tool.
        response = self.requests.get(
            self.project_mrs_url,
            params=fields,
        )

        self.response_ok("find merge request", response)

        mrs = response.json()
        out = []
        for mr in mrs:
            if SHARED_LABEL in (mr.get("labels") or []):
                out.append(mr)

        return (out, mrs)

    def find_single_mr(self, fields) -> dict:
        (mrs_own, mrs_all) = self.find_mrs_with_fields(fields)

        if mrs_own:
            mr = mrs_own[0]
            mr_url = mr.get("web_url") or "<unknown url>"
            LOG.info(
                "Found existing merge request: %s",
                mr_url,
            )
            return mr

        if mrs_all:
            mr_url = mrs_all[0].get("web_url") or "<unknown url>"

            # If we get here, that means we found an MR for the right
            # branches but it apparently wasn't created by us?
            # That makes it not safe to proceed.
            raise GitlabException(
                f"An existing merge request {mr_url} was found, but it was apparently "
                "not created by mirror-tool! Refusing to update. Please close the MR manually "
                "(if it is safe to do so), then re-run the tool."
            )

        # If we get here, that means we didn't find any MR at all which
        # is unexpected.
        raise GitlabException(
            "Failed to create MR due to conflict, "
            "but also failed to locate an existing MR!"
        )

    def create_or_update_mr(self, create_fn, update_fn, find_fields):
        if create_fn():
            return

        LOG.info("GitLab merge request seems to already exist, searching...")
        mr = self.find_single_mr(find_fields)
        update_fn(mr)

    def revision_in_remote_branch(self, revision: str, branch: str) -> bool:
        """Returns True if 'revision' appears to be reachable from remote 'branch'."""

        # Make sure we have latest version of that branch in a local ref...
        self.run_git_silent(
            [
                "git",
                "fetch",
                self.gitlab_info.push_url_final,
                f"+refs/heads/{branch}:refs/mirror-tool/dest-branch",
            ],
            f"fetch remote branch {branch}",
        )

        # Is that revision already reachable from target branch?
        # Note: this will also fail if 'revision' isn't even recognizable as a revision.
        # But in that case we still know it's not in the dest branch, so returning
        # False is reasonable.
        proc = self.run_cmd(
            [
                "git",
                "merge-base",
                "--is-ancestor",
                revision,
                "refs/mirror-tool/dest-branch",
            ],
            check=False,
        )
        if proc.returncode == 0:
            LOG.info(
                "Revision %s is already reachable from remote %s.",
                revision,
                branch,
            )
            return True

        return False
