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
