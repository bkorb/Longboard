#!/usr/bin/env python

import asyncio
from websockets import ConnectionClosedError, ConnectionClosedOK
from websockets.server import serve
from pyvesc.protocol.base import VESCMessage
from Serial.longboard_demo import serial_handler
import functools

CONNECTIONS = set()

async def consumer_handler(websocket, connection):
    try:
        async for message in websocket:
            print(message)
            connection.write(message)
        print("CONSUMER DONE")

    except asyncio.CancelledError:
        print("Consumer Cancelled")
        raise
    except ConnectionClosedError:
        print("Connection Closed")
        raise
    except ConnectionClosedOK:
        print("Connection Closed")
        raise


async def producer_handler(websocket, connection):
    try:
        ptask = connection.producer()
        async for message in ptask:
            await websocket.send(message)
        print("PRODUCER DONE")
    except asyncio.CancelledError:
        print("Producer Cancelled")
        ptask.cancel()
        raise
    except ConnectionClosedError:
        print("Connection Closed")
        raise
    except ConnectionClosedOK:
        print("Connection Closed")
        raise

async def handler(websocket, connection=None, loop=None):
    for con in CONNECTIONS:
            if con.closed:
                CONNECTIONS.remove(con)
    if len(CONNECTIONS) > 0:
        await websocket.send("Only one connection allowed at a time")
        await websocket.close()
        print("Only one connection allowed at a time")
        return
    else:
        CONNECTIONS.add(websocket)
    task1 = loop.create_task(consumer_handler(websocket, connection))
    task2 = loop.create_task(producer_handler(websocket, connection))

    try:
        await task1
        await task2
    except (ConnectionClosedOK, ConnectionClosedError):
        print("HANDLER ERROR")
        task1.cancel()
        task2.cancel()
        CONNECTIONS.remove(websocket)

async def main(loop):
    try:
        connection = serial_handler(loop)
        server = await serve(functools.partial(handler, connection=connection, loop=loop), "192.168.0.27", 8765)
        await server.serve_forever()
    except asyncio.CancelledError:
        server.close()
        await server.wait_closed()
        await connection.close()
        print("Connection closed and flushed")

loop = asyncio.get_event_loop()
task = loop.create_task(main(loop))
try:
    loop.run_forever()
except KeyboardInterrupt:
    task.cancel()
    loop.run_until_complete(task)
    for t in asyncio.all_tasks():
        t.cancel()
    loop.run_forever()
    loop.stop()
finally:
    loop.close()