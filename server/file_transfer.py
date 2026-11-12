"""Frontend-owned one-use localhost downloads and streamed browser uploads."""

import logging
import mimetypes
import os
import re
import secrets
import stat
import socket
import tempfile
from concurrent.futures import Future
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import BinaryIO


logger = logging.getLogger(__name__)
MIME_PATTERN = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+(?:;[ -~]*)?")


@dataclass(eq=False)
class FileGrant:
    file: BinaryIO
    metadata: dict
    expires: float


@dataclass(eq=False)
class UploadGrant:
    """One request's staged bytes and thread-safe completion handle.

    The frontend retains ownership until revoke, including after HTTP completion.
    """

    path: str
    file: BinaryIO
    request_id: str
    profile_id: int
    kind: str
    mime_type: str
    expires: float
    completion: Future = field(default_factory=Future)
    connection: object = None
    claimed: bool = False


class FileTransferServer:
    GRANT_SECONDS = 60
    CHUNK_BYTES = 64 * 1024
    MAX_PENDING = 32

    def __init__(self):
        self._lock = threading.RLock()
        self._grants = {}
        self._active = set()
        self._uploads = {}
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
                if len(self._grants) + len(self._active) + len(self._uploads) >= self.MAX_PENDING:
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

    def reserve_upload(self, request_id: str, profile_id: int, kind: str,
                       mime_type: str, directory=None, timeout: float = 120.0):
        """Reserve a one-use PUT URL and disk-backed completion for a tool request."""
        if not request_id or not isinstance(profile_id, int) or profile_id <= 0:
            raise ValueError("Upload requires a request ID and positive profile ID")
        if not MIME_PATTERN.fullmatch(mime_type) or timeout <= 0:
            raise ValueError("Upload requires a valid MIME type and positive timeout")
        with self._lock:
            if self._closed:
                raise RuntimeError("File transfer service is closed")
            self._expire()
            if len(self._grants) + len(self._active) + len(self._uploads) >= self.MAX_PENDING:
                raise ValueError("Too many file transfers; finish an earlier transfer first")
            if self._http is None:
                self._start()
            descriptor, path = tempfile.mkstemp(prefix=".foxmcp-upload-", dir=directory)
            grant = UploadGrant(path, os.fdopen(descriptor, "wb"), request_id,
                                profile_id, kind, mime_type, time.monotonic() + timeout)
            token = secrets.token_urlsafe(32)
            self._uploads[token] = grant
            return token, f"http://127.0.0.1:{self._http.server_port}/uploads/{token}", grant

    def _discard_upload(self, grant):
        """Called under the lock, including while a receiver is blocked on read."""
        if grant.connection is not None:
            try:
                grant.connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        try:
            grant.file.close()
        except OSError:
            # A failed buffered flush must not prevent staging-file cleanup.
            logger.debug("Discarded upload could not be flushed")
        try:
            os.unlink(grant.path)
        except FileNotFoundError:
            pass
        if not grant.completion.done():
            grant.completion.cancel()

    def revoke(self, token):
        with self._lock:
            upload = self._uploads.pop(token, None)
            if upload:
                self._discard_upload(upload)
            grant = self._grants.pop(token, None)
            if grant:
                grant.file.close()

    def _expire(self):
        with self._lock:
            for token, grant in list(self._uploads.items()):
                if grant.expires <= time.monotonic():
                    if not grant.completion.done():
                        grant.completion.set_exception(TimeoutError("Upload deadline expired"))
                    self.revoke(token)
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

            def do_PUT(self):
                origin = self.headers.get("Origin")
                if (self.headers.get("Host") != f"127.0.0.1:{self.server.server_port}"
                        or origin and not re.fullmatch(r"moz-extension://[^/]+", origin)
                        or self.headers.get("Sec-Fetch-Dest", "empty") != "empty"):
                    self.send_error(403)
                    return
                lengths = self.headers.get_all("Content-Length", [])
                if (len(lengths) != 1 or not re.fullmatch(r"[0-9]+", lengths[0])
                        or self.headers.get("Transfer-Encoding")):
                    self.send_error(411)
                    return
                try:
                    remaining = int(lengths[0])
                except ValueError:
                    self.send_error(411)
                    return
                token = self.path.removeprefix("/uploads/")
                with owner._lock:
                    owner._expire()
                    grant = owner._uploads.get(token) if self.path.startswith("/uploads/") else None
                    if grant is None or grant.claimed:
                        self.send_error(404)
                        return
                    if (self.headers.get("Content-Type") != grant.mime_type
                            or self.headers.get("X-FoxMCP-Request-Id") != grant.request_id):
                        self.send_error(403)
                        return
                    grant.claimed = True
                    grant.connection = self.connection
                try:
                    size = remaining
                    while remaining:
                        # Enforce the total deadline as well as an idle timeout.
                        remaining_time = max(0.001, grant.expires - time.monotonic())
                        self.connection.settimeout(min(5, remaining_time))
                        chunk = self.rfile.read(min(owner.CHUNK_BYTES, remaining))
                        if not chunk:
                            raise OSError("Incomplete upload body")
                        with owner._lock:
                            if (owner._uploads.get(token) is not grant
                                    or time.monotonic() >= grant.expires):
                                raise TimeoutError("Upload expired or cancelled")
                            grant.file.write(chunk)
                        remaining -= len(chunk)
                    with owner._lock:
                        if (owner._uploads.get(token) is not grant
                                or time.monotonic() >= grant.expires):
                            raise TimeoutError("Upload expired or cancelled")
                        grant.file.close()
                        grant.connection = None
                        grant.completion.set_result({"path": grant.path, "size": size,
                                                     "type": grant.mime_type})
                    self.send_response(204)
                    self.send_header("Content-Length", "0")
                    self.send_header("Cache-Control", "no-store")
                    self.end_headers()
                except (OSError, ValueError):
                    with owner._lock:
                        if not grant.completion.done():
                            grant.completion.set_exception(OSError("Upload interrupted or expired"))
                        # A failed grant is consumed and cannot be retried.
                        if owner._uploads.pop(token, None) is grant:
                            owner._discard_upload(grant)
                    try:
                        self.send_error(400)
                    except OSError:
                        pass
                finally:
                    with owner._lock:
                        grant.connection = None

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
            for token in list(self._uploads):
                self.revoke(token)
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
