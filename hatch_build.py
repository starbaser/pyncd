'''The build hook that puts the tsncd page into the wheel.

A wheel build copies the built page `PYNCD_TSNCD_BUNDLE` names into
`websocket_transfer/tsncd_bundle/`, which is how the flake passes tsncd's own Nix
output in, and records beside it the revision `PYNCD_TSNCD_REVISION` names, where
the build knows one. The hook fetches nothing: a build that names no page writes no
bundle, as an editable install does, and such an install names its page through
`TSNCD_DIST` at run time, per `websocket_transfer/bundle.py`.
'''
from __future__ import annotations

import json
import os
import pathlib
import shutil
from typing import Any

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

BUNDLE_DIRECTORY = pathlib.Path('websocket_transfer') / 'tsncd_bundle'
BUNDLE_RECORD = 'bundle.json'
SOURCE_ENV_VAR = 'PYNCD_TSNCD_BUNDLE'
REVISION_ENV_VAR = 'PYNCD_TSNCD_REVISION'
# The compiled relay of the npm package, which the Python relay replaces.
SERVER_DIRECTORY = 'server'


class TsncdBundleHook(BuildHookInterface):
    PLUGIN_NAME = 'custom'

    def initialize(self, version: str, build_data: dict[str, Any]) -> None:
        source = os.environ.get(SOURCE_ENV_VAR)
        if self.target_name != 'wheel' or source is None:
            return
        destination = pathlib.Path(self.root) / BUNDLE_DIRECTORY
        copy_bundle(pathlib.Path(source), destination)
        (destination / BUNDLE_RECORD).write_text(json.dumps({
            'revision': os.environ.get(REVISION_ENV_VAR) or None,
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
