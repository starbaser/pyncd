'''Serving the built tsncd page from the relay's own listener.

`pyncd-server` answers HTTP requests for the page bundle and WebSocket upgrades for
the relay on one port, so a page served this way reaches the relay at its own
origin. The served `index.html` carries a `meta` element saying so, which tsncd's
`diagram_protocol.page_server_uri` reads in the browser. tsncd's
`src/data_transfer/page_serving.ts` is the counterpart of this module, and the two
serve the same files with the same marker.
'''
from __future__ import annotations

import http
import pathlib
import urllib.parse
from collections.abc import Callable

from websockets.datastructures import Headers
from websockets.http11 import Request, Response

RELAY_META_NAME = 'tsncd-relay'
SAME_ORIGIN_RELAY = 'same-origin'
RELAY_META_ELEMENT = f'<meta name="{RELAY_META_NAME}" content="{SAME_ORIGIN_RELAY}">'

CONTENT_TYPES = {
    '.html': 'text/html; charset=utf-8',
    '.js': 'text/javascript; charset=utf-8',
    '.map': 'application/json; charset=utf-8',
    '.json': 'application/json; charset=utf-8',
    '.css': 'text/css; charset=utf-8',
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.ico': 'image/x-icon',
    '.woff2': 'font/woff2',
    '.woff': 'font/woff',
    '.ttf': 'font/ttf',
}


def content_type_of(file: pathlib.Path) -> str:
    return CONTENT_TYPES.get(file.suffix.lower(), 'application/octet-stream')


def page_with_relay_marked(page: str) -> str:
    '''`page` with the element that tells the bundle its relay shares the page's origin.'''
    head = page.find('<head>')
    if head == -1:
        raise ValueError('The page holds no <head> element to mark the relay in.')
    after_head = head + len('<head>')
    return page[:after_head] + RELAY_META_ELEMENT + page[after_head:]


def file_for_request_path(directory: pathlib.Path, request_path: str) -> pathlib.Path | None:
    '''The file under `directory` a request path names, or None for a path that leaves
    the directory or names nothing in it.'''
    decoded = urllib.parse.unquote(request_path.split('?', 1)[0])
    relative = 'index.html' if decoded == '/' else decoded.lstrip('/')
    root = directory.resolve()
    resolved = (root / relative).resolve()
    if resolved != root and root not in resolved.parents:
        return None
    return resolved


def text_response(status: http.HTTPStatus, text: str) -> Response:
    body = text.encode('utf-8')
    return Response(status.value, status.phrase, Headers([
        ('Content-Type', 'text/plain; charset=utf-8'),
        ('Content-Length', str(len(body))),
    ]), body)


def page_response(directory: pathlib.Path, request: Request) -> Response:
    '''The HTTP answer to a request for a file of the page served from `directory`.'''
    if request.headers.get('Upgrade', '').lower() == 'websocket':
        raise ValueError('A WebSocket upgrade is answered by the relay, not the page.')
    method = request.headers.get(':method', 'GET')
    file = file_for_request_path(directory, request.path)
    if file is None or not file.is_file():
        return text_response(http.HTTPStatus.NOT_FOUND, 'Not found.')
    content = file.read_bytes()
    if file.name == 'index.html':
        content = page_with_relay_marked(content.decode('utf-8')).encode('utf-8')
    headers = Headers([
        ('Content-Type', content_type_of(file)),
        ('Content-Length', str(len(content))),
        ('Cache-Control', 'no-cache'),
    ])
    return Response(http.HTTPStatus.OK.value, http.HTTPStatus.OK.phrase, headers,
                    b'' if method == 'HEAD' else content)


def make_request_processor(
    directory: pathlib.Path,
) -> Callable[[object, Request], Response | None]:
    '''The `process_request` of `websockets.serve`: a page file for a plain HTTP request,
    and None for a WebSocket upgrade, which the relay then accepts.'''
    def process_request(connection: object, request: Request) -> Response | None:
        if request.headers.get('Upgrade', '').lower() == 'websocket':
            return None
        return page_response(directory, request)
    return process_request
