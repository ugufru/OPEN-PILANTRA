#!/usr/bin/env python3
"""Read the CoCo text screen out of a running XRoar, via its GDB stub.

Start XRoar with -gdb, then:

    python3 tools/screenpeek.py            # dump the 32x16 screen as text
    python3 tools/screenpeek.py "JSON IS"  # poll until that string appears

This exists because screen-capture is unreliable here, and because reading
video RAM is a better instrument anyway: deterministic, greppable, and usable
from a script. Screen RAM is 512 bytes at $0400.

Byte encoding on the VDG text screen: bit 7 clear is a character cell, and the
low 6 bits are the character with $00-$1F being '@A-Z[\\]^_' and $20-$3F being
' !"#$...?'. Bit 7 set is an SG4 graphics cell, shown here as '.' so text stays
legible against the artwork.
"""

import socket
import sys
import time

HOST, PORT = "127.0.0.1", 65520
SCREEN, SIZE, COLS = 0x0400, 512, 32


def checksum(payload):
    return sum(payload.encode()) & 0xFF


def request(sock, payload):
    sock.sendall(("$%s#%02x" % (payload, checksum(payload))).encode())
    buf = b""
    while b"#" not in buf or len(buf.split(b"#")[-1]) < 2:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    sock.sendall(b"+")
    body = buf.split(b"$", 1)[-1].rsplit(b"#", 1)[0]
    return body.decode()


def connect():
    """One connection, reused. XRoar's stub serves a single client at a time,
    so reconnecting per sample wedges it. Attaching also HALTS the CPU, so we
    immediately continue - otherwise the machine sits frozen wherever it was."""
    sock = socket.create_connection((HOST, PORT), timeout=10)
    sock.settimeout(10)
    request(sock, "qSupported")
    resume(sock)
    return sock


def resume(sock):
    """Let the target run. No reply arrives until it next stops."""
    sock.sendall(("$c#%02x" % checksum("c")).encode())


def interrupt(sock):
    """Ctrl-C the target so memory can be read, and drain the stop packet."""
    sock.sendall(b"\x03")
    buf = b""
    while b"#" not in buf or len(buf.split(b"#")[-1]) < 2:
        chunk = sock.recv(4096)
        if not chunk:
            break
        buf += chunk
    sock.sendall(b"+")


def read_screen(sock):
    """Sample video RAM: stop, read, run on again."""
    interrupt(sock)
    raw = bytes.fromhex(request(sock, "m%x,%x" % (SCREEN, SIZE)))
    resume(sock)
    return raw


def decode(raw):
    out = []
    for byte in raw:
        if byte & 0x80:
            out.append(".")            # SG4 graphics cell
        else:
            code = byte & 0x3F
            out.append(chr(code + 64) if code < 32 else chr(code))
    return ["".join(out[r * COLS : (r + 1) * COLS]) for r in range(len(raw) // COLS)]


def main(argv):
    want = argv[1] if len(argv) > 1 else None
    deadline = time.time() + (240 if want else 0)

    try:
        sock = connect()
    except OSError as exc:
        print("could not reach XRoar (is it running with -gdb?): %s" % exc)
        return 2

    while True:
        try:
            rows = decode(read_screen(sock))
        except (OSError, ValueError) as exc:
            print("lost the connection to XRoar: %s" % exc)
            return 2

        if not want:
            for n, row in enumerate(rows):
                print("%2d |%s|" % (n, row))
            return 0

        if any(want in row for row in rows):
            print("FOUND %r on screen:" % want)
            for n, row in enumerate(rows):
                if want in row:
                    print("%2d |%s|" % (n, row))
            return 0

        if time.time() > deadline:
            print("timed out waiting for %r" % want)
            for n, row in enumerate(rows):
                print("%2d |%s|" % (n, row))
            return 1
        time.sleep(1)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
