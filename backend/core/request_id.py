"""Request-ID correlation: an ID per request, echoed in a response header and added to log lines.

Pure ASGI (no BaseHTTPMiddleware, so websockets and streaming are untouched). Detachable: remove
the two lines in main.py and this file; nothing else imports it.
"""
import logging
import re
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

REQUEST_ID_HEADER = 'X-Request-ID'
_HEADER_BYTES = REQUEST_ID_HEADER.lower().encode('latin-1')
_VALID = re.compile(r'[A-Za-z0-9._-]{1,64}')
LOG_FORMAT = '%(levelname)s:%(name)s:[%(request_id)s] %(message)s'

request_id_var: ContextVar[str] = ContextVar('request_id', default='-')


def get_request_id() -> str:
    return request_id_var.get()


def new_request_id() -> str:
    return uuid.uuid4().hex


def accept_request_id(raw: str | None) -> str:
    """Return raw only if it is a safe token (no CR/LF, spaces, over-length); else a new ID."""
    if raw is not None and _VALID.fullmatch(raw):
        return raw
    return new_request_id()


@contextmanager
def use_request_id(value: str | None = None):
    """Set a (fresh) ID for a block, e.g. a background tick, and restore the previous one."""
    token = request_id_var.set(accept_request_id(value))
    try:
        yield request_id_var.get()
    finally:
        request_id_var.reset(token)


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def make_log_formatter() -> logging.Formatter:
    # defaults: a handler without the filter prints '-' instead of raising KeyError
    return logging.Formatter(LOG_FORMAT, defaults={'request_id': '-'})


class RequestIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] not in ('http', 'websocket'):
            await self.app(scope, receive, send)
            return

        raw = None
        for name, value in scope.get('headers', []):
            if name == _HEADER_BYTES:
                try:
                    raw = value.decode('ascii')
                except UnicodeDecodeError:
                    raw = None
                break
        rid = accept_request_id(raw)
        token = request_id_var.set(rid)

        async def send_with_header(message):
            if message['type'] == 'http.response.start':
                headers = [h for h in message.get('headers', []) if h[0].lower() != _HEADER_BYTES]
                headers.append((_HEADER_BYTES, rid.encode('ascii')))
                message = {**message, 'headers': headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_header)
        finally:
            request_id_var.reset(token)
