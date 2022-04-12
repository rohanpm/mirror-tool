#!/usr/bin/env python3
import yaml
import argparse
import sys
import subprocess
from typing import List
from dataclasses import dataclass
import logging

LOG = logging.getLogger('mirror-tool')

@dataclass
class Mirror:
    url: str
    ref: str
    dir: str = 'upstream'


class Config:
    def __init__(self, raw):
        self._raw = raw

    @property
    def mirrors(self) -> List[Mirror]:
        out = []
        for elem in self._raw.get('mirror') or []:
            out.append(Mirror(**elem))
        return out

    @classmethod
    def from_file(cls, filename='project.yaml') -> 'Config':
        with open(filename, 'rt') as f:
            raw = yaml.safe_load(f)
        return cls(raw)


class MirrorTool:
    @property
    def parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        parser.set_defaults(func=self.no_command)
        subparsers = parser.add_subparsers()

        update_local = subparsers.add_parser('update-local',
            help='Create a commit locally updating all mirrors')
        update_local.set_defaults(func=self.update_local)

        return parser

    @property
    def config(self) -> Config:
        return Config.from_file()

    def run_cmd(self, args, check=True):
        LOG.info("+ %s" % ' '.join(args))
        subprocess.run(args, check=check)

    def update_local_mirror(self, mirror: Mirror):
        self.run_cmd(['git', 'fetch', mirror.url, f'+{mirror.ref}:refs/mirror-tool/to-merge'])

        revision = subprocess.check_output(['git', 'rev-parse', 'refs/mirror-tool/to-merge'], text=True).strip()
        now = subprocess.check_output(['date', '-Im', '-u'], text=True)

        self.run_cmd(['git', 'merge', '-s', 'ours', '--no-commit', '--allow-unrelated-histories', 'refs/mirror-tool/to-merge'])
        self.run_cmd(['git', 'rm', '-rf', f'{mirror.dir}/'], check=False)
        self.run_cmd(['git', 'read-tree', f'--prefix={mirror.dir}/', '-u', 'refs/mirror-tool/to-merge'])

        # TODO: we tolerate failure here as meaning "there was nothing to change".
        # But we should really verify that's the reason we failed.
        self.run_cmd(['git', 'commit', '-m', f'merge {mirror.dir} at {now}'], check=False)

    def update_local(self):
        cfg = self.config

        for mirror in cfg.mirrors:
            self.update_local_mirror(mirror)

    def no_command(self):
        LOG.error("Must specify a command (try `--help').")
        sys.exit(72)

    def run(self, args):
        logging.basicConfig(level=logging.WARNING, format="%(message)s")
        LOG.setLevel(logging.INFO)
        p = self.parser.parse_args(args)
        p.func()


def entrypoint():
    MirrorTool().run(sys.argv[1:])
