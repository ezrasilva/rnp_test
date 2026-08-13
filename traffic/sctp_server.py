#!/usr/bin/env python3
import argparse
import json
import socket
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Numbered SCTP echo server")
    parser.add_argument("--bind", required=True)
    parser.add_argument("--port", type=int, default=36421)
    parser.add_argument("--count", type=int, required=True)
    args = parser.parse_args()

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_SCTP) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.bind, args.port))
        server.listen(1)
        connection, peer = server.accept()
        with connection:
            stream = connection.makefile("rwb", buffering=0)
            for _ in range(args.count):
                raw = stream.readline()
                if not raw:
                    raise RuntimeError("SCTP association closed before all messages arrived")
                message = json.loads(raw)
                message["server_monotonic_ns"] = time.monotonic_ns()
                stream.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
                print(json.dumps({"event": "echo", "peer": peer[0], **message}), flush=True)


if __name__ == "__main__":
    main()

