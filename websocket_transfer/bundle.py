'''Where the built tsncd page is.

The wheel carries the page bundle under `websocket_transfer/tsncd_bundle/`, which
`hatch_build.py` writes at build time from the tsncd revision `pyproject.toml` pins,
so an installed pyncd serves and captures diagrams with no tsncd checkout. A
development checkout, whose editable install writes no bundle, names one through
`TSNCD_DIST`, and a caller may name one directly.
'''
from __future__ import annotations

import importlib.resources
import json
import os
import pathlib
from typing import TypedDict

DIST_ENV_VAR = 'TSNCD_DIST'
BUNDLE_DIRECTORY = 'tsncd_bundle'
BUNDLE_RECORD = 'bundle.json'


class BundleRecord(TypedDict):
    '''What `hatch_build.py` writes beside the bundle it copied.'''
    repository: str
    revision: str


def packaged_bundle() -> pathlib.Path | None:
    '''The bundle the installed package carries, or None for an install without one.'''
    directory = pathlib.Path(str(importlib.resources.files('websocket_transfer') / BUNDLE_DIRECTORY))
    return directory if (directory / 'index.html').is_file() else None


def locate_bundle(dist: str | pathlib.Path | None = None) -> pathlib.Path:
    '''The built tsncd page: `dist` where given, then `TSNCD_DIST`, then the packaged bundle.'''
    if dist is not None:
        candidates = [pathlib.Path(dist)]
    elif environment := os.environ.get(DIST_ENV_VAR):
        candidates = [pathlib.Path(environment)]
    else:
        packaged = packaged_bundle()
        if packaged is not None:
            return packaged
        candidates = []
    for candidate in candidates:
        if (candidate / 'index.html').is_file():
            return candidate
    searched = ', '.join(str(candidate) for candidate in candidates) or 'the installed package'
    raise FileNotFoundError(
        f'No built tsncd page found in {searched}. Install pyncd from a wheel, which '
        f'carries the page, or point {DIST_ENV_VAR} at the `dist/` of a tsncd build.')


def bundle_record(bundle: pathlib.Path) -> BundleRecord | None:
    '''The tsncd revision a packaged bundle was built from, or None for a bundle that
    names none, such as a tsncd checkout's own `dist/`.'''
    record = bundle / BUNDLE_RECORD
    if not record.is_file():
        return None
    return json.loads(record.read_text(encoding='utf-8'))
