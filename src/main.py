# Copyright (c) 2026 Nicky
# SPDX-License-Identifier: MIT

"""Entrypoint."""

import asyncio

from dotenv import load_dotenv

load_dotenv()

from server import main

if __name__ == "__main__":
    asyncio.run(main())
