import logging

from ..conf import GitlabMerge
from ..git_info import UpdateInfo
from ..jinja import jinja_args
from .common import GitlabException, GitlabSession

LOG = logging.getLogger("mirror-tool")


class GitlabUpdateSession(GitlabSession):
    def __init__(self, gitlab_merge: GitlabMerge, run_cmd, updates: list[UpdateInfo]):
        super().__init__(gitlab_merge, run_cmd)
        self.gitlab_merge = gitlab_merge
        self.updates = updates
        self.jinja_args = jinja_args(updates=self.updates)

    def ensure_pushed_to_src(self, revision):
        return self.ensure_pushed_to(revision, self.gitlab_merge.src)

    def create_mr(self) -> bool:
        return self.create_mr_with_branches(
            self.gitlab_merge.src, self.gitlab_merge.dest
        )

    def ensure_merge_request_exists(self, revision="HEAD"):
        if self.revision_in_remote_branch(revision, self.gitlab_merge.dest):
            return

        # First have to make sure it's pushed.
        self.ensure_pushed_to_src(revision)

        self.create_or_update_mr(
            create_fn=self.create_mr,
            update_fn=self.update_mr,
            find_fields={
                "state": "opened",
                "source_branch": self.gitlab_merge.src,
                "target_branch": self.gitlab_merge.dest,
            },
        )
