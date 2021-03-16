# Python: Async IO Modern Forms API Client

[![GitHub Release][releases-shield]][releases]
![Project Stage][project-stage-shield]
![Project Maintenance][maintenance-shield]
[![License][license-shield]](LICENSE.md)

[![Build Status][build-shield]][build]
[![Code Coverage][codecov-shield]][codecov]
[![Code Quality][code-quality-shield]][code-quality]

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
    """Example on controlling your Modern Forms Fan device."""
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
