"""Wire format shared by the Helix host and future clients (protocol v1)."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import socket
import struct
from typing import Any

PROTOCOL_VERSION = 1
DISCOVERY_PORT = 49321
MAX_FRAME_BYTES = 1_048_576
KDF_ITERATIONS = 310_000


def canonical_json(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def master_key(password: str) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), b"Helix discovery v1", KDF_ITERATIONS
    )


def client_key(master: bytes, client_id: str) -> bytes:
    return hmac.digest(master, f"client:{client_id}".encode("ascii"), "sha256")


def password_record(password: str) -> dict[str, str | int]:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, KDF_ITERATIONS)
    return {"salt": salt.hex(), "hash": digest.hex(), "iterations": KDF_ITERATIONS}


def password_matches(password: str, record: dict) -> bool:
    try:
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(record["salt"]),
            int(record["iterations"])
        )
        return hmac.compare_digest(actual, bytes.fromhex(record["hash"]))
    except (KeyError, TypeError, ValueError):
        return False


def signature(key: bytes, payload: dict[str, Any]) -> str:
    return hmac.digest(key, canonical_json(payload), "sha256").hex()


def valid_signature(key: bytes, payload: dict[str, Any], proof: str) -> bool:
    return hmac.compare_digest(signature(key, payload), proof)


def receive_exact(connection: socket.socket, length: int) -> bytes:
    result = bytearray()
    while len(result) < length:
        part = connection.recv(length - len(result))
        if not part:
            raise ConnectionError("The remote endpoint closed the connection")
        result.extend(part)
    return bytes(result)


def send_frame(connection: socket.socket, value: dict[str, Any]) -> None:
    data = canonical_json(value)
    if len(data) > MAX_FRAME_BYTES:
        raise ValueError("Frame exceeds the size limit")
    connection.sendall(struct.pack("!I", len(data)) + data)


def receive_frame(connection: socket.socket) -> dict[str, Any]:
    length = struct.unpack("!I", receive_exact(connection, 4))[0]
    if not 0 < length <= MAX_FRAME_BYTES:
        raise ValueError("Invalid frame size")
    value = json.loads(receive_exact(connection, length))
    if not isinstance(value, dict):
        raise ValueError("Frame must contain a JSON object")
    return value
