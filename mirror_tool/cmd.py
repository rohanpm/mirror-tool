#!/usr/bin/env python3
import argparse
import logging
import os
import subprocess
import sys
from dataclasses import asdict
from typing import Optional

import jinja2
from jsonschema.exceptions import ValidationError

from .conf import Config, Mirror
from .git_config import environ_with_git_config
from .git_info import UpdateInfo, get_update_info
from .gitlab import (
    GitlabPromoteSession,
    GitlabUpdateSession,
    render_ci_template_from_config,
)
from .jinja import jinja_args

LOG = logging.getLogger("mirror-tool")


class MirrorTool:
    def __init__(self):
        self.args: Optional[argparse.Namespace] = None
        self._config: Optional[Config] = None

    @property
    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.set_defaults(func=self.no_command)

        parser.add_argument(
            "--conf",
            "-c",
            type=str,
            default=".mirror-tool.yaml",
            help="Path to configuration file for mirror-tool",
        )
        subparsers = parser.add_subparsers()

        validate_config = subparsers.add_parser(
            "validate-config", help="Validate a mirror-tool configuration file"
        )
        validate_config.set_defaults(func=self.validate_config)

        update_local = subparsers.add_parser(
            "update-local", help="Create a commit locally updating all mirrors"
        )
        update_local.set_defaults(func=self.update_local)

        update = subparsers.add_parser(
            "update",
            help=(
                "Create a commit locally updating all mirrors and "
                "push to enabled remote target(s)"
            ),
        )
        update.set_defaults(func=self.update)

        for p in (update_local, update):
            p.add_argument(
                "--allow-empty",
                action="store_true",
                default=False,
                help=(
                    "Create an empty update commit even if there are no "
                    "updates; primarily for testing purposes"
                ),
            )

        promote = subparsers.add_parser(
            "promote",
            help=("Promote formerly merged mirror-tool MRs to an additional branch"),
        )
        promote.set_defaults(func=self.promote)

        # TODO: a command to close outstanding PR if any.

        gitlab_ci_yml = subparsers.add_parser(
            "gitlab-ci-yml",
            help=("Print a recommended GitLab CI configuration to stdout"),
        )
        gitlab_ci_yml.set_defaults(func=self.gitlab_ci_yml)

        return parser

    @property
    def config(self) -> Config:
        if not self._config:
            self._config = Config.from_file(self.args.conf)
        return self._config

    def run_cmd(
        self, args, check=True, silent=False, env=None, capture_output=None
    ) -> subprocess.CompletedProcess:
        if not silent:
            LOG.info("+ %s" % " ".join(args))
        return subprocess.run(args, check=check, env=env, capture_output=capture_output)

    def run_git_cmd(self, *args, **kwargs):
        kwargs["env"] = environ_with_git_config(self.config.git_config, os.environ)
        return self.run_cmd(*args, **kwargs)

    def commitmsg_for_update(self, update: UpdateInfo) -> str:
        jinja_env = jinja2.Environment(
            loader=jinja2.DictLoader({"commitmsg": self.config.commitmsg})
        )
        return jinja_env.get_template("commitmsg").render(jinja_args(**asdict(update)))

    def update_local_mirror(self, mirror: Mirror) -> UpdateInfo:
        self.run_git_cmd(
            ["git", "fetch", mirror.url, f"+{mirror.ref}:refs/mirror-tool/to-merge"]
        )

        revision = subprocess.check_output(
            ["git", "rev-parse", "refs/mirror-tool/to-merge"], text=True
        ).strip()
        update_info = get_update_info(rev_from="HEAD", rev_to=revision, mirror=mirror)

        self.run_git_cmd(
            [
                "git",
                "merge",
                "-s",
                "ours",
                "--no-commit",
                "--allow-unrelated-histories",
                "refs/mirror-tool/to-merge",
            ]
        )

        if os.path.exists(mirror.dir):
            self.run_git_cmd(
                ["git", "rm", "--quiet", "-rf", f"{mirror.dir}/"], check=False
            )

        self.run_git_cmd(
            [
                "git",
                "read-tree",
                f"--prefix={mirror.dir}/",
                "-u",
                "refs/mirror-tool/to-merge",
            ]
        )

        if update_info.changed or self.args.allow_empty:
            commitmsg = self.commitmsg_for_update(update_info)
            commit_cmd = ["git", "commit", "-m", commitmsg]
            if self.args.allow_empty:
                commit_cmd.append("--allow-empty")

            self.run_git_cmd(commit_cmd)

        return update_info

    def update_local(self) -> list[UpdateInfo]:
        cfg = self.config

        updates = []

        for mirror in cfg.mirrors:
            updates.append(self.update_local_mirror(mirror))

        LOG.info("Mirror(s) locally updated.")

        return [u for u in updates if u.changed]

    def update(self):
        updates = self.update_local()

        if not self.config.gitlab_merge.enabled:
            LOG.info("No remote targets are enabled for update.")
            return

        gitlab = GitlabUpdateSession(
            self.config.gitlab_merge, run_cmd=self.run_cmd, updates=updates
        )
        gitlab.ensure_merge_request_exists()

    def promote(self):
        if not self.config.gitlab_promote:
            LOG.info("No remote targets have any promotion rules.")
            return

        for promote in self.config.gitlab_promote:
            LOG.info("Checking %s => %s promotion...", promote.src, promote.dest)
            gitlab = GitlabPromoteSession(promote, run_cmd=self.run_cmd)
            gitlab.ensure_promotion_merge_request_exists()

    def gitlab_ci_yml(self):
        if not self.config.gitlab_merge.enabled:
            LOG.info("GitLab features are not enabled in config.")
            return

        print(render_ci_template_from_config(self.config))

    def validate_config(self):
        try:
            self.config.validate()
        except ValidationError as ex:
            LOG.error(
                "%s: configuration error\n  Path: %s\n  Object: %s\n  Cause: %s",
                self.args.conf,
                ".".join([str(p) for p in ex.absolute_path]) or "<top level of config>",
                ex.instance,
                ex.message,
            )
            sys.exit(80)

        LOG.info(
            "%s is a valid configuration file defining %s mirror(s).",
            self.args.conf,
            len(self.config.mirrors),
        )

    def no_command(self):
        LOG.error("Must specify a command (try `--help').")
        sys.exit(72)

    def run(self, args):
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        LOG.setLevel(logging.INFO)
        self.args = self.parser.parse_args(args)
        self.args.func()


def entrypoint():
    MirrorTool().run(sys.argv[1:])
