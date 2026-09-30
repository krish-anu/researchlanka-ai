from http import HTTPStatus
from io import BytesIO

from src.api.transport.http_server import client_disconnected, json_response


class _ClosedClient:
    def __init__(self) -> None:
        self.sent: list[int] = []
        self.headers: list[tuple[str, str]] = []

    def send_response(self, status: HTTPStatus) -> None:
        self.sent.append(int(status))

    def send_header(self, key: str, value: str) -> None:
        self.headers.append((key, value))

    def end_headers(self) -> None:
        return None

    @property
    def wfile(self) -> BytesIO:
        raise BrokenPipeError(32, "Broken pipe")


def test_closed_client_does_not_raise() -> None:
    handler = _ClosedClient()
    json_response(handler, {"data": []})  # type: ignore[arg-type]
    assert handler.sent == [200]


def test_client_disconnected_recognises_reset() -> None:
    assert client_disconnected(ConnectionResetError(104, "Connection reset"))
    assert not client_disconnected(RuntimeError("query failed"))
