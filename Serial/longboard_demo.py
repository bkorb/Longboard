import asyncio
from pathlib import Path
import sys


class serial_handler:
    def __init__(self, loop):
        asyncio.ensure_future(self.start(loop), loop=loop)

    async def start(self, loop):
        pass

    async def producer(self):
        try:
            while True:
                await asyncio.sleep(2)
                yield "TESTING"
        except asyncio.CancelledError:
            print("Reader Closed")


    async def close(self):
        pass

    def write(self, message):
        print(message)