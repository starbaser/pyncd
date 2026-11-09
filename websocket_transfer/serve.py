'''The `pyncd-server` command.

    pyncd-server [--host HOST] [--port PORT] [--relay-only]

It runs the relay and serves the tsncd page the wheel carries from the same port,
so a browser opened at the printed address reaches both. `--relay-only` serves no
page, and `HOST` and `PORT` in the environment are the defaults of the two options.
tsncd's `tsncd serve` is the same command for the npm package.
'''
from __future__ import annotations

import argparse
import asyncio
import pathlib
import sys

import websocket_transfer.bundle as bundle
import websocket_transfer.websockets_transfer as wst


def parse_arguments(arguments: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='pyncd-server',
        description='Run the diagram relay and serve the tsncd page on one port.')
    parser.add_argument('--host', default=wst.SERVER_HOST,
                        help='the address to bind, HOST in the environment by default')
    parser.add_argument('--port', default=str(wst.SERVER_PORT),
                        help='the port to bind, PORT in the environment by default')
    parser.add_argument('--relay-only', action='store_true',
                        help='run the relay and serve no page')
    return parser.parse_args(arguments)


def page_to_serve(relay_only: bool) -> pathlib.Path | None:
    if relay_only:
        return None
    page = bundle.locate_bundle()
    record = bundle.bundle_record(page)
    if record is not None:
        built = record['revision'] or 'an unrecorded revision'
        print(f'Page built from {record["repository"]} ({record["branch"]}) at {built}.')
    return page


def main(arguments: list[str] | None = None) -> None:
    options = parse_arguments(sys.argv[1:] if arguments is None else arguments)
    port = wst.server_port_from_text(options.port)
    page = page_to_serve(options.relay_only)
    asyncio.run(wst.DataServer().main(options.host, port, page))


if __name__ == '__main__':
    main()
