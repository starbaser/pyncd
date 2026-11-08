'''Check that the relay serves the tsncd page beside its WebSocket on one port.

    python websocket_transfer/validate_page_serving.py

The checks write a stand-in page into a temporary directory, start `DataServer.main`
on a free port with it, fetch the page and an asset over HTTP, refuse a path that
leaves the directory, and exchange a held term over a WebSocket on the same port.
They also check the locator's order and the typewriter escaping tsncd mirrors.
'''
from __future__ import annotations

import asyncio
import http
import json
import os
import pathlib
import socket
import sys
import tempfile
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

import websockets

import data_structure.Term as fd
import websocket_transfer.bundle as bundle
import websocket_transfer.page_serving as page_serving
import websocket_transfer.websockets_transfer as wst

PAGE = ('<!DOCTYPE html>\n<html lang="en">\n<head>\n  <meta charset="UTF-8">\n'
        '<title>tsncd</title></head><body></body></html>\n')


def unused_port() -> int:
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0))
        return listener.getsockname()[1]


def check_marker_and_paths() -> None:
    marked = page_serving.page_with_relay_marked(PAGE)
    expected_start = ('<!DOCTYPE html>\n<html lang="en">\n<head>'
                      '<meta name="tsncd-relay" content="same-origin">\n  <meta charset')
    assert marked.startswith(expected_start), marked[:120]
    try:
        page_serving.page_with_relay_marked('<html></html>')
    except ValueError:
        pass
    else:
        raise AssertionError('A page without a head was marked.')
    directory = pathlib.Path(tempfile.gettempdir()) / 'tsncd-stand-in'
    assert page_serving.file_for_request_path(directory, '/') == (directory / 'index.html').resolve()
    assert page_serving.file_for_request_path(directory, '/assets/a.js?v=1') == (
        directory / 'assets' / 'a.js').resolve()
    assert page_serving.file_for_request_path(directory, '/../x') is None
    assert page_serving.file_for_request_path(directory, '/a/%2e%2e/%2e%2e/x') is None
    assert page_serving.content_type_of(pathlib.Path('x.js')) == 'text/javascript; charset=utf-8'
    assert page_serving.content_type_of(pathlib.Path('x.bin')) == 'application/octet-stream'


def check_locator_order() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        explicit = pathlib.Path(temporary) / 'explicit'
        named = pathlib.Path(temporary) / 'named'
        for directory in (explicit, named):
            directory.mkdir()
            (directory / 'index.html').write_text(PAGE, encoding='utf-8')
        previous = os.environ.get(bundle.DIST_ENV_VAR)
        os.environ[bundle.DIST_ENV_VAR] = str(named)
        try:
            assert bundle.locate_bundle(explicit) == explicit
            assert bundle.locate_bundle() == named
            os.environ[bundle.DIST_ENV_VAR] = str(pathlib.Path(temporary) / 'missing')
            try:
                bundle.locate_bundle()
            except FileNotFoundError as error:
                assert bundle.DIST_ENV_VAR in str(error)
            else:
                raise AssertionError('A missing page was located.')
        finally:
            if previous is None:
                del os.environ[bundle.DIST_ENV_VAR]
            else:
                os.environ[bundle.DIST_ENV_VAR] = previous
        assert bundle.bundle_record(named) is None
        (named / bundle.BUNDLE_RECORD).write_text(
            json.dumps({'repository': 'r', 'revision': 'v'}), encoding='utf-8')
        assert bundle.bundle_record(named) == {'repository': 'r', 'revision': 'v'}


def check_typewriter_escaping() -> None:
    assert fd.escape_typewriter('a_b') == 'a\\_b'
    assert fd.escape_typewriter('x\\y^z~{w}$&#%') == (
        'x\\textbackslash{}y\\textasciicircum{}z\\textasciitilde{}'
        '\\{w\\}\\$\\&\\#\\%')
    name = fd.DynamicName('pkg.Cls[T]_1', settings=fd.DynamicNameSettings(typewriter=True))
    assert name.body_latex() == '\\texttt{pkg.Cls[T]\\_1}', name.body_latex()


def fetch(url: str, method: str = 'GET') -> tuple[int, str, bytes]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, response.headers.get('Content-Type', ''), response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.headers.get('Content-Type', ''), error.read()


async def check_served_page() -> None:
    with tempfile.TemporaryDirectory() as temporary:
        page = pathlib.Path(temporary)
        (page / 'index.html').write_text(PAGE, encoding='utf-8')
        (page / 'assets').mkdir()
        (page / 'assets' / 'main.abc.js').write_text('console.log(1);\n', encoding='utf-8')
        port = unused_port()
        server = asyncio.create_task(wst.DataServer().main('127.0.0.1', port, page))
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(50):
                try:
                    status, content_type, body = await asyncio.to_thread(fetch, f'{base}/')
                    break
                except (urllib.error.URLError, ConnectionError):
                    await asyncio.sleep(0.1)
            else:
                raise AssertionError('The relay did not start serving its page.')
            assert status == http.HTTPStatus.OK, status
            assert content_type == 'text/html; charset=utf-8', content_type
            assert b'<meta name="tsncd-relay" content="same-origin">' in body
            status, content_type, body = await asyncio.to_thread(
                fetch, f'{base}/assets/main.abc.js')
            assert (status, content_type, body) == (
                200, 'text/javascript; charset=utf-8', b'console.log(1);\n')
            status, _, _ = await asyncio.to_thread(fetch, f'{base}/assets/missing.js')
            assert status == http.HTTPStatus.NOT_FOUND, status
            status, _, body = await asyncio.to_thread(fetch, f'{base}/', 'HEAD')
            assert (status, body) == (200, b''), (status, body)

            async with websockets.connect(f'ws://127.0.0.1:{port}') as socket_:
                update = {'msgType': 'dataUpdate', 'data': '{"model":"served-page"}',
                          'settings': {}}
                await socket_.send(json.dumps(update))
                assert json.loads(await socket_.recv())['msgType'] == 'DataReceived'
                await socket_.send(json.dumps({'msgType': 'dataRequest'}))
                assert json.loads(await socket_.recv()) == update
        finally:
            server.cancel()
            try:
                await server
            except asyncio.CancelledError:
                pass


def main() -> None:
    check_marker_and_paths()
    check_locator_order()
    check_typewriter_escaping()
    asyncio.run(check_served_page())
    print('ok: the relay serves the page, the locator orders its sources, and typewriter '
          'names escape as tsncd does')


if __name__ == '__main__':
    main()
