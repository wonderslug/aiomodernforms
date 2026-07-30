"""CLI entry point for running a mock Modern Forms fan."""

from __future__ import annotations

import argparse
import logging

from aiohttp import web

from .generations import PROFILES
from .server import create_app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the mock fan server."""
    parser = argparse.ArgumentParser(
        description="Run a mock Modern Forms fan HTTP server."
    )
    parser.add_argument(
        "--generation",
        required=True,
        choices=sorted(PROFILES),
        help="Fan hardware generation to emulate.",
    )
    parser.add_argument(
        "--breeze",
        action="store_true",
        help="Enable breeze (wind) mode support.",
    )
    parser.add_argument(
        "--light",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=(
            "Enable light control (default: enabled). "
            "Use --no-light to simulate a fan-only unit."
        ),
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host/interface to listen on (default: 0.0.0.0).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to listen on (default: 8080).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    """Run the mock fan server until interrupted."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    args = _parse_args(argv)
    profile = PROFILES[args.generation]
    app = create_app(profile, breeze=args.breeze, light=args.light)
    print(
        f"Mock fan listening on {args.host}:{args.port}"
        f" (generation={profile.name}, breeze={'on' if args.breeze else 'off'},"
        f" light={'on' if args.light else 'off'})"
    )
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
