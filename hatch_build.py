'''The build hook that puts the tsncd page into the wheel.

A wheel build writes `websocket_transfer/tsncd_bundle/` from one of two sources and
records which. `PYNCD_TSNCD_BUNDLE` names a built page to copy, which is how the
flake passes tsncd's own Nix output in, and `PYNCD_TSNCD_REVISION` may name the
revision that page was built from. Without a named page the hook clones the tip of
the tsncd branch `[tool.pyncd.tsncd]` names and builds the page with npm, so
`uv build` from a checkout needs git, Node 24 and the network.
`PYNCD_SKIP_TSNCD_BUNDLE=1` builds a wheel without the page, and an editable install
writes no bundle, so a development checkout names its page through `TSNCD_DIST`, per
`websocket_transfer/bundle.py`.
'''
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import tempfile
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

BUNDLE_DIRECTORY = pathlib.Path('websocket_transfer') / 'tsncd_bundle'
BUNDLE_RECORD = 'bundle.json'
SOURCE_ENV_VAR = 'PYNCD_TSNCD_BUNDLE'
REVISION_ENV_VAR = 'PYNCD_TSNCD_REVISION'
SKIP_ENV_VAR = 'PYNCD_SKIP_TSNCD_BUNDLE'
# The compiled relay of the npm package, which the Python relay replaces.
SERVER_DIRECTORY = 'server'


class TsncdBundleHook(BuildHookInterface):
    PLUGIN_NAME = 'custom'

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        if self.target_name != 'wheel' or os.environ.get(SKIP_ENV_VAR):
            return
        source = os.environ.get(SOURCE_ENV_VAR)
        if version == 'editable' and source is None:
            return
        page = self.metadata.config['tool']['pyncd']['tsncd']
        destination = pathlib.Path(self.root) / BUNDLE_DIRECTORY
        if source is not None:
            copy_bundle(pathlib.Path(source), destination)
            revision = os.environ.get(REVISION_ENV_VAR) or None
        else:
            revision = build_bundle(page['repository'], page['branch'], destination)
        (destination / BUNDLE_RECORD).write_text(json.dumps({
            'repository': page['repository'],
            'branch': page['branch'],
            'revision': revision,
        }, indent=2) + '\n', encoding='utf-8')
        build_data.setdefault('artifacts', []).append(f'{BUNDLE_DIRECTORY.as_posix()}/**')


def copy_bundle(source: pathlib.Path, destination: pathlib.Path) -> None:
    if not (source / 'index.html').is_file():
        raise FileNotFoundError(f'{source} holds no index.html, so it is not a tsncd page.')
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(SERVER_DIRECTORY))
    # A page copied out of the Nix store arrives read-only, directories included,
    # and the record is written beside it.
    for path in (destination, *destination.rglob('*')):
        path.chmod(path.stat().st_mode | 0o200)


def build_bundle(repository: str, branch: str, destination: pathlib.Path) -> str:
    '''Build the page from the tip of `branch` and return the revision that was built.'''
    with tempfile.TemporaryDirectory(prefix='tsncd-build-') as temporary:
        checkout = pathlib.Path(temporary) / 'tsncd'
        subprocess.run(
            ['git', 'clone', '--quiet', '--depth', '1', '--branch', branch,
             repository, str(checkout)], check=True)
        revision = subprocess.run(
            ['git', 'rev-parse', 'HEAD'], cwd=checkout, check=True,
            capture_output=True, text=True).stdout.strip()
        subprocess.run(['npm', 'ci', '--ignore-scripts', '--no-audit', '--no-fund'],
                       cwd=checkout, check=True)
        subprocess.run(['npm', 'run', 'build'], cwd=checkout, check=True)
        copy_bundle(checkout / 'dist', destination)
        return revision
