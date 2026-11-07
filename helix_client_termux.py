"""Termux client for the Helix v1 LAN terminal protocol."""

from __future__ import annotations

import argparse
import base64
import binascii
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import uuid

from helix_protocol import (
    DISCOVERY_PORT, PROTOCOL_VERSION, client_key, master_key,
    password_matches, password_record, receive_frame, send_frame,
    signature, valid_signature,
)

CLIENT_PORT = 49322
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path.home() / ".config" / "helix-client-termux"
CONFIG_PATH = DATA_DIR / "client_config.json"
CERT_PATH = DATA_DIR / "client.crt"
KEY_PATH = DATA_DIR / "client.key"


def save_json(path: Path, value: dict) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def certificate_fingerprint() -> str:
    der = ssl.PEM_cert_to_DER_cert(CERT_PATH.read_text(encoding="ascii"))
    return hashlib.sha256(der).hexdigest()


def create_certificate(identity: str) -> str:
    """Generate a per-device TLS identity with Termux's OpenSSL package."""
    if shutil.which("openssl") is None:
        raise RuntimeError("OpenSSL command missing. Run: pkg install -y openssl-tool")
    try:
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-sha256",
            "-nodes", "-days", "3650", "-keyout", str(KEY_PATH),
            "-out", str(CERT_PATH), "-subj", f"/CN=Helix Client {identity}",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        KEY_PATH.chmod(0o600)
        CERT_PATH.chmod(0o600)
        return certificate_fingerprint()
    except (OSError, subprocess.CalledProcessError, ValueError):
        KEY_PATH.unlink(missing_ok=True)
        CERT_PATH.unlink(missing_ok=True)
        raise


def first_run() -> dict:
    DATA_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    DATA_DIR.chmod(0o700)
    if CERT_PATH.exists() or KEY_PATH.exists():
        raise RuntimeError("Certificate files exist without client_config.json. Resolve this state manually.")
    print("Helix Client first-time setup (Android Termux)")
    while True:
        name = input("Device name: ").strip()
        if 0 < len(name) <= 80 and all(ord(char) >= 32 for char in name):
            break
        print("Use a name between 1 and 80 printable characters.")
    while True:
        password = getpass.getpass("Shared Helix password: ")
        again = getpass.getpass("Repeat password: ")
        if password and password == again:
            break
        print("Password is empty or confirmation does not match.")
    identity = str(uuid.uuid4())
    fingerprint = create_certificate(identity)
    config = {
        "version": 1,
        "client_id": identity,
        "name": name,
        "platform": "termux",
        "port": CLIENT_PORT,
        "login": password_record(password),
        "auth_key": client_key(master_key(password), identity).hex(),
        "certificate_sha256": fingerprint,
    }
    save_json(CONFIG_PATH, config)
    print(f"Registered {name}. Client ID: {identity}")
    return config


def validate_config(config: dict) -> None:
    if not isinstance(config, dict) or config.get("version") != 1:
        raise ValueError("Unsupported client_config.json format")
    try:
        if config.get("platform") != "termux" or config.get("port") != CLIENT_PORT:
            raise ValueError("This build requires a Termux client on the standard port")
        if str(uuid.UUID(config["client_id"])) != config["client_id"]:
            raise ValueError("Invalid client ID")
        if not isinstance(config.get("name"), str) or not 0 < len(config["name"]) <= 80:
            raise ValueError("Invalid device name")
        for field in ("auth_key", "certificate_sha256"):
            if len(bytes.fromhex(config[field])) != 32:
                raise ValueError(f"Invalid {field}")
        if not isinstance(config.get("login"), dict) or not {"salt", "hash", "iterations"}.issubset(config["login"]):
            raise ValueError("Invalid local password record")
    except (KeyError, TypeError) as error:
        raise ValueError("Client configuration is incomplete") from error
    if not CERT_PATH.is_file() or not KEY_PATH.is_file():
        raise ValueError("Client certificate or key is missing; restore it before starting")
    actual = certificate_fingerprint()
    if not hmac.compare_digest(actual, config["certificate_sha256"]):
        raise ValueError("Client certificate changed; the indexed host would reject it")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return first_run()
    DATA_DIR.chmod(0o700)
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    validate_config(config)
    password = getpass.getpass("Helix Client password: ")
    if not password_matches(password, config["login"]):
        raise PermissionError("Wrong password")
    return config


def local_address(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
        return parsed.version == 4 and (parsed.is_private or parsed.is_loopback)
    except ValueError:
        return False


class HelixClient:
    def __init__(self, config: dict):
        self.config = config
        self.stop = threading.Event()
        self.session_lock = threading.Lock()
        self.active_connection: ssl.SSLSocket | None = None
        self.udp_socket: socket.socket | None = None
        self.tcp_socket: socket.socket | None = None
        self.tls_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.tls_context.minimum_version = ssl.TLSVersion.TLSv1_2
        self.tls_context.load_cert_chain(str(CERT_PATH), str(KEY_PATH))

    def start(self) -> None:
        udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            udp.bind(("0.0.0.0", DISCOVERY_PORT))
            udp.settimeout(0.5)
            tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            tcp.bind(("0.0.0.0", CLIENT_PORT))
            tcp.listen(5)
            tcp.settimeout(0.5)
        except OSError:
            udp.close()
            tcp.close()
            raise
        self.udp_socket, self.tcp_socket = udp, tcp
        threading.Thread(target=self.serve_discovery, daemon=True).start()
        threading.Thread(target=self.serve_sessions, daemon=True).start()
        print(f"Helix Client ready: {self.config['name']}")
        print(f"Discovery UDP {DISCOVERY_PORT}; terminal TCP {CLIENT_PORT}. Run index on the Debian host.")
        print("Type help for local commands. Detach with Ctrl+B then D.")

    def serve_discovery(self) -> None:
        assert self.udp_socket is not None
        while not self.stop.is_set():
            try:
                raw, address = self.udp_socket.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            if not local_address(address[0]):
                continue
            try:
                request = json.loads(raw)
                if not isinstance(request, dict) or request.get("type") != "discover":
                    continue
                if request.get("version") != PROTOCOL_VERSION:
                    continue
                nonce = request.get("nonce")
                if not isinstance(nonce, str) or len(nonce) != 32 or any(c not in "0123456789abcdef" for c in nonce):
                    continue
                offer = {
                    "type": "offer", "version": PROTOCOL_VERSION, "nonce": nonce,
                    "client_id": self.config["client_id"], "name": self.config["name"],
                    "platform": "termux", "port": CLIENT_PORT,
                    "certificate_sha256": self.config["certificate_sha256"],
                }
                offer["proof"] = signature(bytes.fromhex(self.config["auth_key"]), offer)
                self.udp_socket.sendto(json.dumps(offer, ensure_ascii=False).encode("utf-8"), address)
            except (OSError, TypeError, ValueError, json.JSONDecodeError):
                continue

    def serve_sessions(self) -> None:
        assert self.tcp_socket is not None
        while not self.stop.is_set():
            try:
                connection, address = self.tcp_socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            if not local_address(address[0]) or not self.session_lock.acquire(blocking=False):
                connection.close()
                continue
            threading.Thread(target=self.handle_connection, args=(connection, address[0]), daemon=True).start()

    def handle_connection(self, plain: socket.socket, address: str) -> None:
        try:
            plain.settimeout(10)
            with self.tls_context.wrap_socket(plain, server_side=True) as connection:
                self.active_connection = connection
                nonce = secrets.token_hex(32)
                send_frame(connection, {"type": "challenge", "nonce": nonce})
                reply = receive_frame(connection)
                expected = {"type": "authenticate", "nonce": nonce, "client_id": self.config["client_id"]}
                if reply.get("type") != "authenticate" or not valid_signature(
                    bytes.fromhex(self.config["auth_key"]), expected, reply.get("proof", "")
                ):
                    print(f"Rejected unauthenticated connection from {address}.")
                    return
                send_frame(connection, {"type": "authenticated"})
                opening = receive_frame(connection)
                if opening.get("type") != "open":
                    raise ValueError("Expected open frame")
                cols, rows = opening.get("cols"), opening.get("rows")
                if type(cols) is not int or type(rows) is not int or not 20 <= cols <= 500 or not 10 <= rows <= 200:
                    raise ValueError("Invalid terminal size")
                connection.settimeout(None)
                self.stream_shell(connection, cols, rows)
        except (OSError, ValueError, ConnectionError, PermissionError) as error:
            if not self.stop.is_set():
                print(f"Session ended ({address}): {error}")
        finally:
            self.active_connection = None
            self.session_lock.release()
            try:
                plain.close()
            except OSError:
                pass

    def stream_shell(self, connection: ssl.SSLSocket, cols: int, rows: int) -> None:
        worker = BASE_DIR / "termux_pty_worker.py"
        process = subprocess.Popen(
            [sys.executable, str(worker), str(cols), str(rows)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            bufsize=0, cwd=str(Path.home()),
        )
        assert process.stdin is not None and process.stdout is not None
        send_lock = threading.Lock()
        finished = threading.Event()
        send_frame(connection, {"type": "opened"})
        print("Termux shell session opened.")

        def output_loop() -> None:
            try:
                while not finished.is_set():
                    output = os.read(process.stdout.fileno(), 4096)
                    if not output:
                        break
                    with send_lock:
                        send_frame(connection, {"type": "output", "data": base64.b64encode(output).decode("ascii")})
            except (OSError, ValueError):
                pass
            finally:
                finished.set()
                try:
                    with send_lock:
                        send_frame(connection, {"type": "closed"})
                except OSError:
                    pass
                try:
                    connection.shutdown(socket.SHUT_RD)
                except OSError:
                    pass

        output_thread = threading.Thread(target=output_loop, daemon=True)
        output_thread.start()
        try:
            while not finished.is_set() and not self.stop.is_set():
                frame = receive_frame(connection)
                kind = frame.get("type")
                if kind == "input":
                    raw = base64.b64decode(frame["data"], validate=True)
                    if raw:
                        process.stdin.write(raw)
                elif kind == "resize":
                    # The host does not yet emit resize frames automatically.
                    pass
                elif kind == "close":
                    break
                else:
                    raise ValueError("Unknown terminal frame")
        except (OSError, ConnectionError, ValueError, KeyError, binascii.Error):
            pass
        finally:
            finished.set()
            try:
                process.stdin.close()
            except OSError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            print("Termux shell session closed.")

    def change_password(self) -> None:
        old = getpass.getpass("Current client password: ")
        if not password_matches(old, self.config["login"]):
            print("Wrong password.")
            return
        new = getpass.getpass("New client password: ")
        again = getpass.getpass("Repeat new password: ")
        if not new or new != again:
            print("Password is empty or confirmation does not match.")
            return
        self.config["login"] = password_record(new)
        save_json(CONFIG_PATH, self.config)
        print("Client unlock password changed. Existing host pairing remains valid.")

    def run_console(self) -> None:
        try:
            while not self.stop.is_set():
                try:
                    command = input("client> ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if command == "help":
                    print("help | status | password | quit")
                elif command == "status":
                    busy = "remote session active" if self.session_lock.locked() else "waiting"
                    print(f"{self.config['name']} [{self.config['client_id']}] - {busy}")
                elif command == "password":
                    self.change_password()
                elif command == "quit":
                    break
                elif command:
                    print("Unknown command. Type help.")
        finally:
            self.stop.set()
            for listener in (self.udp_socket, self.tcp_socket, self.active_connection):
                if listener:
                    try:
                        listener.close()
                    except OSError:
                        pass
            print("Helix Client stopped.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Helix Android Termux client")
    parser.add_argument("--setup", action="store_true", help="register this device without starting the listener")
    args = parser.parse_args()
    if os.name != "posix" or "com.termux" not in os.environ.get("PREFIX", ""):
        print("This Helix client build runs in Android Termux only.", file=sys.stderr)
        return 1
    if sys.version_info < (3, 10):
        print("Helix Client requires Python 3.10 or newer.", file=sys.stderr)
        return 1
    try:
        if args.setup:
            if CONFIG_PATH.exists():
                config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                validate_config(config)
                print(f"Already registered: {config['name']}")
            else:
                first_run()
            return 0
        config = load_config()
        client = HelixClient(config)
        client.start()
        client.run_console()
        return 0
    except (OSError, ValueError, RuntimeError, PermissionError, json.JSONDecodeError) as error:
        print(f"Helix Client could not start: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
