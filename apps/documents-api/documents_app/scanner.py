import socket
from typing import IO, Protocol

from documents_app.config import Settings


class ScanError(Exception):
    pass


class MalwareScanner(Protocol):
    def scan(self, source: IO[bytes]) -> tuple[bool, str | None]: ...


class LocalCleanScanner:
    """Explicit development-only scanner used after upload validation."""

    def scan(self, source: IO[bytes]) -> tuple[bool, str | None]:
        source.seek(0)
        return True, None


class ClamAVScanner:
    def __init__(self, host: str, port: int, chunk_size: int) -> None:
        self.host = host
        self.port = port
        self.chunk_size = chunk_size

    def scan(self, source: IO[bytes]) -> tuple[bool, str | None]:
        source.seek(0)
        try:
            with socket.create_connection((self.host, self.port), timeout=10) as connection:
                connection.sendall(b"zINSTREAM\0")
                while chunk := source.read(self.chunk_size):
                    connection.sendall(len(chunk).to_bytes(4, "big"))
                    connection.sendall(chunk)
                connection.sendall((0).to_bytes(4, "big"))
                result = connection.recv(4096).decode("utf-8", errors="replace").strip("\0\r\n")
        except OSError as exc:
            raise ScanError("Malware scanner is unavailable.") from exc
        if result.endswith(" OK"):
            return True, None
        if " FOUND" in result:
            return False, result.rsplit(":", 1)[-1].strip()
        raise ScanError("Malware scanner returned an invalid response.")


def scanner_from_settings(settings: Settings) -> MalwareScanner:
    if settings.malware_scanner_mode == "local_clean":
        return LocalCleanScanner()
    if settings.clamav_host is None:
        raise ScanError("Malware scanner is not configured.")
    return ClamAVScanner(
        settings.clamav_host, settings.clamav_port, settings.upload_chunk_size_bytes
    )
