"""One-use localhost downloads for loading server files into Firefox."""

import logging
import mimetypes
import os
import re
import secrets
import stat
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import BinaryIO


logger = logging.getLogger(__name__)
MIME_PATTERN = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:;[ -~]*)?")


@dataclass(eq=False)
class FileGrant:
    file: BinaryIO
    metadata: dict
    expires: float


class FileTransferServer:
    GRANT_SECONDS = 60
    CHUNK_BYTES = 64 * 1024
    MAX_PENDING = 32

    def __init__(self):
        self._lock = threading.RLock()
        self._grants = {}
        self._active = set()
        self._http = None
        self._thread = None
        self._closed = False

    def grant(self, path, mime_type=None):
        if mime_type is not None and not MIME_PATTERN.fullmatch(mime_type):
            raise ValueError("mime_type must be a valid ASCII MIME type without control characters")
        name = os.path.basename(os.path.abspath(path))
        media_type = mime_type or mimetypes.guess_type(name)[0] or "application/octet-stream"
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        descriptor = os.open(path, flags)
        try:
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode):
                raise ValueError("path must name a regular file")
            handle = os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
        metadata = {"name": name, "type": media_type.lower(), "size": info.st_size,
                    "lastModified": info.st_mtime_ns // 1_000_000}
        grant = FileGrant(handle, metadata, time.monotonic() + self.GRANT_SECONDS)
        try:
            with self._lock:
                if self._closed:
                    raise RuntimeError("File transfer service is closed")
                self._expire()
                if len(self._grants) + len(self._active) >= self.MAX_PENDING:
                    raise ValueError("Too many file transfers; finish an earlier transfer first")
                if self._http is None:
                    self._start()
                token = secrets.token_urlsafe(32)
                self._grants[token] = grant
                url = f"http://127.0.0.1:{self._http.server_port}/files/{token}"
                return token, url, metadata
        except BaseException:
            handle.close()
            raise

    def revoke(self, token):
        with self._lock:
            grant = self._grants.pop(token, None)
            if grant:
                grant.file.close()

    def _expire(self):
        with self._lock:
            for token, grant in list(self._grants.items()):
                if grant.expires <= time.monotonic():
                    self.revoke(token)

    def _start(self):
        owner = self

        class Server(ThreadingHTTPServer):
            daemon_threads = True
            block_on_close = False

            def service_actions(self):
                owner._expire()

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                super().setup()
                self.connection.settimeout(5)

            def log_message(self, *_args):
                pass  # Request paths contain bearer tokens.

            def do_GET(self):
                origin = self.headers.get("Origin")
                if (self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                        or origin and not re.fullmatch(r"moz-extension://[^/]+", origin)
                        or self.headers.get("Sec-Fetch-Dest", "empty") != "empty"):
                    self.send_error(403)
                    return
                token = self.path.removeprefix("/files/")
                with owner._lock:
                    owner._expire()
                    grant = owner._grants.pop(token, None) if self.path.startswith("/files/") else None
                    if grant:
                        owner._active.add(grant)
                if grant is None:
                    self.send_error(404)
                    return
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", grant.metadata["type"])
                    self.send_header("Content-Length", str(grant.metadata["size"]))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.end_headers()
                    remaining = grant.metadata["size"]
                    while remaining and not owner._closed:
                        chunk = grant.file.read(min(owner.CHUNK_BYTES, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
                except (OSError, ValueError):
                    logger.debug("File transfer interrupted")
                finally:
                    with owner._lock:
                        owner._active.discard(grant)
                        grant.file.close()

        self._http = Server(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._http.serve_forever,
                                        kwargs={"poll_interval": 0.2}, daemon=True,
                                        name="foxmcp-files")
        self._thread.start()

    def close(self):
        with self._lock:
            self._closed = True
            http = self._http
        if http:
            http.shutdown()
            http.server_close()
            self._thread.join(timeout=2)
        with self._lock:
            for grant in list(self._grants.values()) + list(self._active):
                grant.file.close()
            self._grants.clear()
            self._active.clear()
