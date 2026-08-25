"""CLI entry point for running a mock Modern Forms fan."""

from __future__ import annotations

import argparse
import logging

from aiohttp import web

from .generations import PROFILES
from .server import create_app, create_gen4_app


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the mock fan server."""
    parser = argparse.ArgumentParser(
        description="Run a mock Modern Forms fan HTTP server."
    )
    parser.add_argument(
        "--generation",
        required=True,
        choices=sorted([*PROFILES, "gen4"]),
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
        "--lights",
        type=int,
        default=1,
        help=(
            "Number of light fixtures on the mock Gen4 fan (default: 1). "
            "Only applies with --generation gen4."
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
    if args.generation == "gen4":
        app = create_gen4_app(lights=args.lights)
        print(
            f"Mock fan listening on {args.host}:{args.port}"
            f" (generation=gen4, lights={args.lights})"
        )
    else:
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
