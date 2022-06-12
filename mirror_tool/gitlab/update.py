import logging

from ..conf import GitlabMerge
from ..git_info import UpdateInfo
from ..jinja import jinja_args
from .common import GitlabSession

LOG = logging.getLogger("mirror-tool")


class GitlabUpdateSession(GitlabSession):
    def __init__(
        self,
        gitlab_merge: GitlabMerge,
        run_cmd,
        updates: list[UpdateInfo],
        dry_run: bool = False,
    ):
        super().__init__(gitlab_merge, run_cmd, dry_run)
        self.gitlab_merge = gitlab_merge
        self.updates = updates
        self.jinja_args = jinja_args(updates=self.updates)

    def ensure_pushed_to_src(self, revision):
        return self.ensure_pushed_to(revision, self.gitlab_merge.src)

    def create_mr(self) -> bool:
        return self.create_mr_with_branches(
            self.gitlab_merge.src, self.gitlab_merge.dest
        )

    def is_mr_uptodate(self, mr, revision) -> bool:
        web_url = mr.get("web_url") or "<unknown url>"
        LOG.info("Checking existing MR %s ...", web_url)

        mr_revision = mr["sha"]

        # Make sure we have the MR revision.
        self.run_git_silent(
            [
                "git",
                "fetch",
                self.gitlab_info.push_url_final,
                f"+{mr_revision}:refs/mirror-tool/existing-mr",
            ],
            f"fetch remote revision {mr_revision}",
        )

        if (
            self.run_cmd(
                ["git", "diff", "--quiet", revision, mr_revision], check=False
            ).returncode
            != 0
        ):
            # There are differences in content => it's not up-to-date
            LOG.info(
                "MR %s needs an update: there are differences in content.", web_url
            )
            return False

        # TODO: there could still be differences in the mutable MR attributes.
        # What to do about it?
        # - If we insist on updating MRs for any difference, it can create a lot of noise.
        # - If we don't update MRs, then config changes don't take effect until the next
        #   time an MR is created with different content.
        # - Does it need to be configurable?
        LOG.info("MR %s does not need an update.", web_url)
        return True

    def ensure_merge_request_exists(self, revision="HEAD"):
        if self.revision_in_remote_branch(revision, self.gitlab_merge.dest):
            return

        # Let's see if there's already an MR by us between src and dest branch.
        find_fields = {
            "state": "opened",
            "source_branch": self.gitlab_merge.src,
            "target_branch": self.gitlab_merge.dest,
        }
        (ours, _) = self.find_mrs_with_fields(find_fields)
        if ours and self.is_mr_uptodate(ours[0], revision):
            # Don't need to do anything.
            return

        # First have to make sure it's pushed.
        self.ensure_pushed_to_src(revision)

        self.create_or_update_mr(
            create_fn=self.create_mr,
            update_fn=self.update_mr,
            find_fields=find_fields,
        )
