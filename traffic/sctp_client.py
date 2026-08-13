#!/usr/bin/env python3
import argparse
import json
import socket
import statistics
import time


def main() -> None:
    parser = argparse.ArgumentParser(description="Rate-controlled numbered SCTP client")
    parser.add_argument("--bind", required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=36421)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument("--rate", type=float, default=10.0, help="messages per second")
    args = parser.parse_args()
    if args.count < 1 or args.rate <= 0:
        parser.error("count and rate must be positive")

    rtts = []
    next_send = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_SCTP) as client:
        client.bind((args.bind, 0))
        client.settimeout(3)
        client.connect((args.host, args.port))
        stream = client.makefile("rwb", buffering=0)
        for sequence in range(1, args.count + 1):
            delay = next_send - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            sent_ns = time.monotonic_ns()
            stream.write(json.dumps({"sequence": sequence, "client_send_monotonic_ns": sent_ns},
                                    separators=(",", ":")).encode() + b"\n")
            response = json.loads(stream.readline())
            received_ns = time.monotonic_ns()
            if response["sequence"] != sequence:
                raise RuntimeError(f"sequence mismatch: expected {sequence}, got {response['sequence']}")
            rtt_ns = received_ns - sent_ns
            rtts.append(rtt_ns)
            print(json.dumps({"event": "response", "client_receive_monotonic_ns": received_ns,
                              "rtt_ns": rtt_ns, **response}), flush=True)
            next_send += 1 / args.rate

    print(json.dumps({"event": "summary", "sent": args.count, "received": len(rtts),
                      "loss": args.count - len(rtts),
                      "rtt_median_ns": int(statistics.median(rtts))}), flush=True)


if __name__ == "__main__":
    main()

