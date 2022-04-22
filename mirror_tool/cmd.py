#!/usr/bin/env python3
import argparse
import sys
import subprocess
import logging
import os
from typing import Optional

from jsonschema.exceptions import ValidationError


from .conf import Config, Mirror
from .gitlab import GitlabSession

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

        # TODO: a command to close outstanding PR if any.
        # TODO: a command to generate gitlab pipeline config?

        return parser

    @property
    def config(self) -> Config:
        if not self._config:
            self._config = Config.from_file(self.args.conf)
        return self._config

    def run_cmd(self, args, check=True, silent=False):
        if not silent:
            LOG.info("+ %s" % " ".join(args))
        subprocess.run(args, check=check)

    def update_local_mirror(self, mirror: Mirror):
        self.run_cmd(
            ["git", "fetch", mirror.url, f"+{mirror.ref}:refs/mirror-tool/to-merge"]
        )

        revision = subprocess.check_output(
            ["git", "rev-parse", "refs/mirror-tool/to-merge"], text=True
        ).strip()
        now = subprocess.check_output(["date", "-Im", "-u"], text=True)

        self.run_cmd(
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
            self.run_cmd(["git", "rm", "--quiet", "-rf", f"{mirror.dir}/"], check=False)

        self.run_cmd(
            [
                "git",
                "read-tree",
                f"--prefix={mirror.dir}/",
                "-u",
                "refs/mirror-tool/to-merge",
            ]
        )

        # TODO: we tolerate failure here as meaning "there was nothing to change".
        # But we should really verify that's the reason we failed.
        self.run_cmd(
            ["git", "commit", "-m", f"merge {mirror.dir} at {now}"], check=False
        )

    def update_local(self):
        cfg = self.config

        for mirror in cfg.mirrors:
            self.update_local_mirror(mirror)

        LOG.info("Mirror(s) locally updated.")

    def update(self):
        self.update_local()

        if not self.config.gitlab_merge.enabled:
            LOG.info("No remote target(s) are enabled for update.")
            return

        gitlab = GitlabSession(self.config.gitlab_merge, run_cmd=self.run_cmd)
        gitlab.ensure_merge_request_exists()

    def validate_config(self):
        try:
            self.config.validate()
        except ValidationError as ex:
            LOG.error(
                "%s: configuration error\n  Path: %s\n  Object: %s\n  Cause: %s",
                self.args.conf,
                " ".join([str(p) for p in ex.absolute_path]),
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
