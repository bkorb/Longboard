import asyncio
import serial_asyncio
from pathlib import Path
import sys
import pyvesc


can_id = 124
class serial_handler:
    def __init__(self, device, loop):
        asyncio.ensure_future(self.start(device, loop), loop=loop)

    async def start(self, device, loop):
        reader, writer = await serial_asyncio.open_serial_connection(url=device, baudrate=115200, loop=loop)
        self.reader = reader
        self.writer = writer

    async def producer(self):
        buf = bytearray(b'')
        try:
            while True:
                msg = await self.reader.readuntil(b'\x03')
                buf.extend(msg)
                if len(buf) >= 32:
                    (response, consumed) = pyvesc.decode(bytes(buf))
                    if response is not None:
                        buf = buf[consumed:]
                        yield response
        except asyncio.CancelledError:
            print("Reader Closed")


    async def close(self):
        await self.writer.drain()
        self.writer.close()
        await self.writer.wait_closed()

    def write(self, message):
        self.writer.write(message)