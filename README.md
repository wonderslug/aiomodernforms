# Python: Async IO Modern Forms API Client

[![Continuous Integration](https://github.com/wonderslug/aiomodernforms/actions/workflows/ci.yml/badge.svg?branch=master)](https://github.com/wonderslug/aiomodernforms/actions/workflows/ci.yml)
![Codecov](https://img.shields.io/codecov/c/github/wonderslug/aiomodernforms)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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
