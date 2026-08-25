# Python: Async IO Modern Forms API Client

![GitHub Workflow Status](https://img.shields.io/github/workflow/status/wonderslug/aiomodernforms/Continuous%20Integration)
![Codecov](https://img.shields.io/codecov/c/github/wonderslug/aiomodernforms)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![PyPI](https://img.shields.io/pypi/v/aiomodernforms)

Asynchronous Python client for Modern Forms Fans.

## About

This package allows you to control and monitor Modern Forms fans
programmatically. It is mainly created to allow third-party programs to automate
the behavior of the Modern Forms fans

## Installation

```bash
pip install aiomodernforms
```

## Usage

```python
"""Asynchronous Python client for Async IO Modern Forms fan."""

import asyncio
from datetime import datetime, timedelta

import aiomodernforms
from aiomodernforms.const import LIGHT_POWER_ON


async def main():
    """Turn on the fan light."""
    async with aiomodernforms.ModernFormsDevice("192.168.3.197") as fan:
        await fan.update()
        print(fan.status)
        await fan.light(
            on=LIGHT_POWER_ON,
            brightness=50,
            sleep=datetime.now() + timedelta(minutes=2),
        )
        print(fan.status)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
```

## Reporting compatibility issues

WAC and Modern Forms fans span several hardware generations, and not every
generation behaves identically. If this library doesn't work correctly
against your fan, run `diagnose.py` against it and paste the output into a
[GitHub issue](https://github.com/wonderslug/aiomodernforms/issues):

```bash
python diagnose.py <fan-ip-address>
# or, from a checkout with a dev environment set up:
make diagnose HOST=<fan-ip-address>
```

This prints a Markdown report — parsed capability flags, the raw API
responses, and any response fields this library doesn't recognize yet — that
helps pinpoint model/generation differences. It redacts your account email,
AWS identity, MAC address, device name, and certificate ID, and never
includes the fan's IP address, so the output is safe to paste as-is. Still,
give it a quick read before posting.

## Mock fan for development

To develop or test a client (such as a Home Assistant integration) against
this API without real hardware, run a mock fan that speaks the same wire
protocol:

```bash
python -m mock_fan --generation gen3 --breeze --port 8080
# or
make mock-fan GENERATION=gen1_2 PORT=8081
```

`--generation` is `gen1_2` or `gen3` and is required; `--breeze` optionally
enables breeze/wind mode support; `--no-light` simulates a fan-only unit
with no light kit (light is on by default). Point your client at the
printed host/port exactly as you would a real fan.

For Gen4, use `--generation gen4 --lights N` (`--breeze`/`--no-light` don't apply —
Gen4 always exposes breeze fields on the fan fixture, and light count is controlled
by `--lights`, default 1; `--lights 0` simulates a fan with no light kit).
