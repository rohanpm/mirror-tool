import logging

from ..conf import GitlabPromote
from ..jinja import jinja_args
from .common import SHARED_LABEL, GitlabException, GitlabSession

LOG = logging.getLogger("mirror-tool")


class GitlabPromoteSession(GitlabSession):
    def __init__(self, gitlab_promote: GitlabPromote, run_cmd):
        super().__init__(gitlab_promote, run_cmd)
        self.gitlab_promote = gitlab_promote

        # TODO: can we put something useful in the jinja context?
        self.jinja_args = jinja_args(updates=[])

    def ensure_pushed_to_workbranch(self, revision):
        return self.ensure_pushed_to(revision, self.gitlab_promote.working_branch)

    def create_mr(self) -> bool:
        return self.create_mr_with_branches(
            self.gitlab_promote.working_branch, self.gitlab_promote.dest
        )

    def find_merged_mr(self) -> dict:
        LOG.info("Looking for previous MRs to %s...", self.gitlab_promote.src)
        (mrs_own, _) = self.find_mrs_with_fields(
            {
                "target_branch": self.gitlab_promote.src,
                "labels": SHARED_LABEL,
                "state": "merged",
            },
        )

        if mrs_own:
            mr = mrs_own[0]
            mr_url = mr.get("web_url") or "<unknown url>"
            LOG.info(
                "Found existing merge request: %s",
                mr_url,
            )
            return mr

    def ensure_promotion_merge_request_exists(self):
        # Locate the latest submitted MR by ourselves to the target branch.
        src_mr = self.find_merged_mr()

        if not src_mr:
            LOG.info("No eligible MR for promotion.")
            return

        # Make this object available to Jinja contexts.
        self.jinja_args["src_mr"] = src_mr

        revision = src_mr["merge_commit_sha"]
        LOG.debug("Should promote: %s", revision)

        if self.revision_in_remote_branch(revision, self.gitlab_promote.dest):
            return

        self.ensure_pushed_to_workbranch(revision)

        # # Create promotion MR if it didn't already exist.
        # if self.create_mr():
        #     return

        # LOG.info("GitLab promotion merge request seems to already exist, searching...")
        # mr = self.find_promotion_mr()
        # self.update_mr(mr)
        self.create_or_update_mr(
            create_fn=self.create_mr,
            update_fn=self.update_mr,
            find_fields={
                "state": "opened",
                "source_branch": self.gitlab_promote.working_branch,
                "target_branch": self.gitlab_promote.dest,
            },
        )
