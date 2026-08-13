from __future__ import annotations

import argparse
import logging
from pathlib import Path

from .server import create_server
from .storage import TelemetryStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="PQC distributed metrics collector")
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve")
    serve.add_argument("--listen", default="0.0.0.0:50051")
    serve.add_argument("--data-dir", type=Path, default=Path("runs"))
    serve.add_argument("--insecure", action="store_true")
    serve.add_argument("--ca", type=Path)
    serve.add_argument("--cert", type=Path)
    serve.add_argument("--key", type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    storage = TelemetryStorage(args.data_dir)
    server = create_server(args.listen, storage, insecure=args.insecure,
                           ca=args.ca, cert=args.cert, key=args.key)
    server.start()
    logging.info("collector listening=%s data_dir=%s insecure=%s",
                 args.listen, args.data_dir, args.insecure)
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        server.stop(grace=2)


if __name__ == "__main__":
    main()

