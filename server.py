#!/usr/bin/env python

import asyncio
from websockets import ConnectionClosedError, ConnectionClosedOK
from websockets.server import serve
from pyvesc.protocol.base import VESCMessage
from Serial.longboard_serial import serial_handler
from pyvesc.VESC.messages import GetValues, SetRPM, SetCurrent, SetRotorPositionMode, GetRotorPosition, GetVersion
import pyvesc
import functools
import json

can_id = 124
values = pyvesc.encode_request(GetValues)
values2 = pyvesc.encode_request(GetValues(can_id=can_id))
drive = pyvesc.encode(SetRPM(1000))
drive2 = pyvesc.encode(SetRPM(1000, can_id=can_id))
CONNECTIONS = set()

def stop_motors(connection):
    print("Stopping Motors")
    connection.write(pyvesc.encode(SetCurrent(0)))
    connection.write(pyvesc.encode(SetCurrent(0, can_id=can_id)))

def clean(attr):
    if isinstance(attr, bytes):
        return int.from_bytes(attr, "big")
    return attr

async def consumer_handler(websocket, connection):
    try:
        async for message in websocket:
            print(message)
            connection.write(drive)
            connection.write(drive2)
            connection.write(values)
            connection.write(values2)
        print("CONSUMER DONE")
        raise ConnectionClosedError(None, None)
    except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
        raise


async def producer_handler(websocket, connection):
    try:
        ptask = connection.producer()
        async for message in ptask:
            fields = message._field_names
            jdata = {field: clean(getattr(message, field)) for field in fields}
            print(jdata)
            await websocket.send(json.dumps(jdata))
        print("PRODUCER DONE")
        raise ConnectionClosedError(None, None)
    except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
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
    except (ConnectionClosedOK, ConnectionClosedError, asyncio.CancelledError, Exception):
        print("HANDLER ERROR")
        task1.cancel()
        task2.cancel()
        stop_motors(connection)
        CONNECTIONS.remove(websocket)
        try:
            await task1
        except Exception:
            pass
        try:
            await task2
        except Exception:
            pass

async def main(loop):
    try:
        connection = serial_handler("/dev/ttyACM0", loop)
        server = await serve(functools.partial(handler, connection=connection, loop=loop), "192.168.0.27", 8765)
        await server.serve_forever()
    except asyncio.CancelledError:
        server.close()
        await server.wait_closed()
        stop_motors(connection)
        await connection.close()
        print("Connection closed and flushed")

loop = asyncio.get_event_loop()
task = loop.create_task(main(loop))
try:
    loop.run_forever()
except KeyboardInterrupt:
    task.cancel()
    loop.run_until_complete(task)
    loop.stop()
finally:
    loop.close()