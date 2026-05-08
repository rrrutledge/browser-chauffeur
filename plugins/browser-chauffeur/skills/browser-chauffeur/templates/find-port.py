"""Find an available CDP port from a candidate range.

Usage: python find-port.py [--start 9222] [--count 5]

Prints the first available port to stdout. Exits 1 if none in range are free.
"""

import argparse
import socket
import sys


def is_port_available(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            s.connect(("localhost", port))
            return False
        except (ConnectionRefusedError, socket.timeout, OSError):
            return True


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=9222)
    p.add_argument("--count", type=int, default=5)
    args = p.parse_args()

    for port in range(args.start, args.start + args.count):
        if is_port_available(port):
            print(port)
            return 0

    print(
        f"No available port in range {args.start}-{args.start + args.count - 1}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
