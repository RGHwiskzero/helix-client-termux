"""Single-threaded PTY bridge for a remote Termux Bash session."""

from __future__ import annotations

import errno
import fcntl
import os
from pathlib import Path
import pty
import select
import shutil
import signal
import struct
import sys
import termios


def write_all(fd: int, data: bytes) -> None:
    while data:
        count = os.write(fd, data)
        data = data[count:]


def main() -> int:
    cols, rows = map(int, sys.argv[1:3])
    bash = shutil.which("bash")
    if not bash:
        print("Termux Bash was not found.", file=sys.stderr)
        return 1
    rcfile = Path(__file__).with_name("remote_shell_rc.sh")
    os.environ["HELIX_REMOTE_SHELL"] = "1"
    child, master = pty.fork()
    if child == 0:
        os.chdir(Path.home())
        os.execv(bash, [bash, "--noprofile", "--rcfile", str(rcfile), "-i"])

    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))

    def stop_child() -> None:
        try:
            os.killpg(child, signal.SIGHUP)
        except ProcessLookupError:
            pass

    def stop_worker(_signum, _frame) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop_worker)
    try:
        while True:
            readable, _, _ = select.select([sys.stdin.fileno(), master], [], [])
            if master in readable:
                try:
                    data = os.read(master, 4096)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not data:
                    break
                write_all(sys.stdout.fileno(), data)
            if sys.stdin.fileno() in readable:
                data = os.read(sys.stdin.fileno(), 4096)
                if not data:
                    break
                write_all(master, data)
    finally:
        stop_child()
        os.close(master)
        os.waitpid(child, 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
