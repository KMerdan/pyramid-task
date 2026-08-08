from __future__ import annotations

import hashlib
import json
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from pyramid_core import (
    PyramidError,
    graph_snapshot,
    load_assurance_bundle,
    load_project,
    node_doc_path,
    node_map,
    project_paths,
)
from pyramid_visualizer import build_visualization_html, load_visualization_graph, visualization_snapshot


def _json_bytes(value: dict[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _semantic_etag(value: dict[str, Any]) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


class LiveGraphState:
    """Track only complete, validated graph publications.

    Runtime mutations publish a canonical head before compiling `.pyramid/graph.json`.
    Watching both boundaries lets the browser keep its last valid projection while also
    reporting a committed context whose presentation is delayed or invalid.
    """

    def __init__(self, project: str | Path, graph: dict[str, Any], poll_interval: float = 0.25) -> None:
        self.project = Path(project).expanduser().resolve()
        self.paths = project_paths(self.project)
        self.poll_interval = poll_interval
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._watcher: threading.Thread | None = None
        self._graph = graph
        self._body = _json_bytes(graph)
        self._etag = _semantic_etag(graph)
        self._observed_signature = self._published_signature()
        self._pending_failure: tuple[tuple[tuple[int | None, int | None], ...], str] | None = None
        self._sequence = 0
        self._event: dict[str, Any] = {
            "type": "ready",
            "sequence": self._sequence,
            "graph_version": graph["graph_version"],
            "context_id": graph.get("context", {}).get("id"),
            "etag": self._etag,
        }

    def _published_signature(self) -> tuple[tuple[int | None, int | None], ...]:
        signatures = []
        for key in ("graph", "head", "state"):
            try:
                stat = self.paths[key].stat()
                signatures.append((stat.st_mtime_ns, stat.st_size))
            except FileNotFoundError:
                signatures.append((None, None))
        return tuple(signatures)

    def start(self) -> None:
        if self._watcher and self._watcher.is_alive():
            return
        self._watcher = threading.Thread(target=self._watch, name="pyramid-live-watch", daemon=True)
        self._watcher.start()

    def stop(self) -> None:
        self._stop.set()
        with self._condition:
            self._condition.notify_all()
        if self._watcher and self._watcher is not threading.current_thread():
            self._watcher.join(timeout=max(1.0, self.poll_interval * 4))

    @property
    def stopped(self) -> bool:
        return self._stop.is_set()

    def snapshot(self) -> tuple[bytes, str, dict[str, Any]]:
        with self._condition:
            return self._body, self._etag, self._graph

    def event(self) -> dict[str, Any]:
        with self._condition:
            return dict(self._event)

    def wait_for_event(self, after_sequence: int, timeout: float = 15.0) -> dict[str, Any] | None:
        with self._condition:
            self._condition.wait_for(
                lambda: self._sequence > after_sequence or self._stop.is_set(),
                timeout=timeout,
            )
            if self._sequence > after_sequence:
                return dict(self._event)
            return None

    def allowed_source(self, relative_path: str) -> Path | None:
        with self._condition:
            allowed = {
                node.get("source_path")
                for node in self._graph.get("nodes", [])
                if node.get("source_path")
            }
        if relative_path not in allowed:
            return None
        candidate = (self.project / relative_path).resolve()
        if not candidate.is_relative_to(self.project) or not candidate.is_file():
            return None
        return candidate

    def refresh(self) -> bool:
        signature = self._published_signature()
        if signature == self._observed_signature:
            return False
        try:
            paths, plan, runtime_state = load_project(self.project)
            manifest, baseline, assurance = load_assurance_bundle(paths, plan)
            raw = self.paths["graph"].read_bytes()
            candidate = json.loads(raw)
            if not isinstance(candidate, dict):
                raise PyramidError("Published graph must contain a JSON object")
            required = {"schema", "graph_version", "intent", "nodes", "edges", "summary", "lifecycle"}
            missing = sorted(required - candidate.keys())
            if missing:
                raise PyramidError("Published graph is missing: " + ", ".join(missing))
            if candidate["graph_version"] != runtime_state["graph_version"]:
                raise PyramidError(
                    "Published graph version does not match canonical runtime state "
                    f"({candidate['graph_version']} != {runtime_state['graph_version']})"
                )
            expected = graph_snapshot(plan, runtime_state, baseline, assurance, manifest)
            by_id = node_map(plan)
            for item in expected["nodes"]:
                item["source_path"] = str(node_doc_path(paths, by_id[item["id"]]).relative_to(paths["root"]))
            comparable_candidate = dict(candidate)
            comparable_expected = dict(expected)
            comparable_candidate.pop("generated_at", None)
            comparable_expected.pop("generated_at", None)
            if comparable_candidate != comparable_expected:
                raise PyramidError("Published graph does not match the canonical runtime projection")
        except (OSError, json.JSONDecodeError, PyramidError) as exc:
            message = str(exc)
            if self._pending_failure == (signature, message):
                self._observed_signature = signature
                self._pending_failure = None
                self._publish_error(message)
            else:
                self._pending_failure = (signature, message)
            return False

        presentation = visualization_snapshot(candidate)
        body = _json_bytes(presentation)
        etag = _semantic_etag(presentation)
        with self._condition:
            self._observed_signature = signature
            self._pending_failure = None
            if etag == self._etag:
                if self._event.get("type") == "graph-error":
                    self._sequence += 1
                    self._event = {
                        "type": "ready",
                        "sequence": self._sequence,
                        "graph_version": presentation["graph_version"],
                        "context_id": presentation.get("context", {}).get("id"),
                        "etag": etag,
                    }
                    self._condition.notify_all()
                return False
            self._graph = presentation
            self._body = body
            self._etag = etag
            self._sequence += 1
            self._event = {
                "type": "graph",
                "sequence": self._sequence,
                "graph_version": presentation["graph_version"],
                "context_id": presentation.get("context", {}).get("id"),
                "etag": etag,
                "generated_at": candidate.get("generated_at"),
            }
            self._condition.notify_all()
        return True

    def _publish_error(self, message: str) -> None:
        with self._condition:
            if self._event.get("type") == "graph-error" and self._event.get("message") == message:
                return
            self._sequence += 1
            self._event = {
                "type": "graph-error",
                "sequence": self._sequence,
                "graph_version": self._graph["graph_version"],
                "context_id": self._graph.get("context", {}).get("id"),
                "etag": self._etag,
                "message": message,
            }
            self._condition.notify_all()

    def _watch(self) -> None:
        while not self._stop.wait(self.poll_interval):
            self.refresh()


class _LiveHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _event_bytes(event: dict[str, Any]) -> bytes:
    event_type = event["type"]
    payload = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"id: {event['sequence']}\nevent: {event_type}\ndata: {payload}\n\n".encode("utf-8")


def _handler_for(state: LiveGraphState, html: bytes) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _is_loopback_host(self) -> bool:
            host = self.headers.get("Host", "").lower()
            name, separator, port = host.partition(":")
            return name in {"127.0.0.1", "localhost"} and (not separator or port.isdecimal())

        def _security_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
                "connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'",
            )

        def _send(self, body: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._is_loopback_host():
                self._send(
                    b"Loopback Host header required\n",
                    "text/plain; charset=utf-8",
                    HTTPStatus.MISDIRECTED_REQUEST,
                )
                return
            parsed = urlparse(self.path)
            if parsed.path in {"/", "/index.html"}:
                self._send(html, "text/html; charset=utf-8")
                return
            if parsed.path == "/api/graph":
                body, etag, _ = state.snapshot()
                if self.headers.get("If-None-Match") == f'"{etag}"':
                    self.send_response(HTTPStatus.NOT_MODIFIED)
                    self.send_header("ETag", f'"{etag}"')
                    self.send_header("Cache-Control", "no-store")
                    self._security_headers()
                    self.end_headers()
                    return
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("ETag", f'"{etag}"')
                self._security_headers()
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/events":
                self._events()
                return
            if parsed.path.startswith("/project/"):
                relative = unquote(parsed.path[len("/project/") :])
                source = state.allowed_source(relative)
                if source is None:
                    self._send(b"Not found\n", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)
                    return
                self._send(source.read_bytes(), "text/markdown; charset=utf-8")
                return
            if parsed.path == "/favicon.ico":
                self._send(b"", "image/x-icon", HTTPStatus.NO_CONTENT)
                return
            self._send(b"Not found\n", "text/plain; charset=utf-8", HTTPStatus.NOT_FOUND)

        def _events(self) -> None:
            try:
                after = int(self.headers.get("Last-Event-ID", "-1"))
            except ValueError:
                after = -1
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self._security_headers()
            self.end_headers()
            try:
                current = state.event()
                self.wfile.write(_event_bytes(current))
                self.wfile.flush()
                after = current["sequence"]
                while not state.stopped:
                    event = state.wait_for_event(after, timeout=15.0)
                    if event is None:
                        self.wfile.write(b": keep-alive\n\n")
                    else:
                        self.wfile.write(_event_bytes(event))
                        after = event["sequence"]
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                return

    return Handler


class LiveVisualizationServer:
    def __init__(
        self,
        project: str | Path,
        *,
        port: int = 0,
        poll_interval: float = 0.25,
    ) -> None:
        if not 0 <= port <= 65535:
            raise PyramidError("port must be between 0 and 65535")
        if poll_interval < 0.05:
            raise PyramidError("poll-interval must be at least 0.05 seconds")
        graph = load_visualization_graph(project)
        self.state = LiveGraphState(project, graph, poll_interval=poll_interval)
        html = build_visualization_html(graph, live=True).encode("utf-8")
        try:
            self.httpd = _LiveHTTPServer(("127.0.0.1", port), _handler_for(self.state, html))
        except OSError as exc:
            raise PyramidError(f"Could not start live visualization on 127.0.0.1:{port}: {exc}") from exc
        _, bound_port = self.httpd.server_address[:2]
        self.url = f"http://127.0.0.1:{bound_port}/"
        self._serving = threading.Event()

    def describe(self) -> dict[str, Any]:
        _, etag, graph = self.state.snapshot()
        return {
            "status": "live",
            "url": self.url,
            "project": str(self.state.project),
            "graph_version": graph["graph_version"],
            "context": graph.get("context"),
            "nodes": len(graph["nodes"]),
            "etag": etag,
            "poll_interval": self.state.poll_interval,
            "canonical_commit": ".pyramid/head.json",
            "publication": ".pyramid/graph.json",
        }

    def open_browser(self) -> None:
        webbrowser.open(self.url)

    def serve_forever(self) -> None:
        self.state.start()
        self._serving.set()
        try:
            self.httpd.serve_forever(poll_interval=0.2)
        finally:
            self._serving.clear()
            self.state.stop()
            self.httpd.server_close()

    def shutdown(self) -> None:
        self.state.stop()
        if self._serving.is_set():
            self.httpd.shutdown()
        else:
            self.httpd.server_close()
