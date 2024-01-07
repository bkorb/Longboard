#!/usr/bin/env python

import asyncio
from websockets import ConnectionClosedError, ConnectionClosedOK
from websockets.server import serve
from pyvesc.protocol.base import VESCMessage
from Serial.longboard_serial import serial_handler
from pyvesc.VESC.messages import VedderCmd as vc
from pyvesc.VESC.messages import GetValues, SetRPM, SetCurrent, SetRotorPositionMode, GetRotorPosition, GetVersion
from time import time
import pyvesc
import functools
import json


def clean(attr):
    if isinstance(attr, bytes):
        return int.from_bytes(attr, "big")
    return attr


SETTINGS_PATH = "/home/bkorb/Longboard/settings.json"


def load_settings(settings = {}):
    try:
        with open(SETTINGS_PATH, 'r') as openfile:
            settings.update(json.load(openfile))
    except FileNotFoundError:
        pass
    return settings


def save_settings(settings):
    with open(SETTINGS_PATH, "w") as outfile:
        json.dump(settings, outfile)


class Server:
    def __init__(self):
        self.can_id = 124
        self.CONNECTIONS = set()
        self.CURRENT = 0
        self.TARGET = 0
        self.VALUE_DATA = GetValues()
        self.SETTINGS = load_settings({
            "Max Acceleration": 5000,
            "Max Deceleration": 15000,
        })

    def start(self):
        self.loop = asyncio.get_event_loop()
        self.connection = serial_handler("/dev/ttyACM0", self.loop)
        webserver = self.loop.create_task(self.handle_webserver())
        board = self.loop.create_task(self.handle_board())
        try:
            self.loop.run_forever()
        except KeyboardInterrupt:
            webserver.cancel()
            board.cancel()
            self.loop.run_until_complete(webserver)
            self.loop.stop()
        finally:
            self.loop.close()

    def write_both(self, message):
        try:
            self.connection.write(pyvesc.encode(message))
            setattr(message, 'can_id', self.can_id)
            self.connection.write(pyvesc.encode(message))
        except Exception:
            self.connection.write(pyvesc.encode_request(message))
            setattr(message, 'can_id', self.can_id)
            self.connection.write(pyvesc.encode_request(message))

    def stop_motors(self):
        print("Stopping Motors")
        self.TARGET = 0
        self.write_both(SetCurrent(0))

    async def parse_command(self, websocket, id, fields):
        try:
            if id == "SET_TARGET":
                self.TARGET = fields['rpm']
            elif id == "GET_TARGET":
                await websocket.send(json.dumps({'id': id, 'fields': {'rpm': self.TARGET}}))
            elif id == "SET_SETTINGS":
                self.SETTINGS = fields
                save_settings(self.SETTINGS)
                await websocket.send(json.dumps({'id': id, 'fields': self.SETTINGS}))
            elif id == "GET_SETTINGS":
                await websocket.send(json.dumps({'id': id, 'fields': self.SETTINGS}))
        except Exception:
            raise

    async def consumer_handler(self, websocket):
        try:
            async for message in websocket:
                try:
                    jmessage = json.loads(message)
                    id = jmessage['id']
                    fields = jmessage['fields']
                    obj = VESCMessage.msg_type(vc[id].value)(**fields)
                    self.write_both(obj)
                except KeyError:
                    try:
                        await self.parse_command(websocket, id, fields)
                    except KeyError:
                        print(f"Non valid message: {message}")
                    except Exception:
                        print(f"Connection Failure {message}")
                except Exception:
                    print(f"Connection Failure {message}")
            print("CONSUMER DONE")
            raise ConnectionClosedError(None, None)
        except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
            raise


    async def producer_handler(self, websocket):
        try:
            ptask = self.connection.producer()
            async for message in ptask:
                fields = message._field_names
                jdata = {field: clean(getattr(message, field)) for field in fields}
                mdata = {"id": vc(int(message.id)).name, "fields": jdata}
                if mdata["id"] == "COMM_GET_VALUES":
                    self.VALUE_DATA = message
                await websocket.send(json.dumps(mdata))
            print("PRODUCER DONE")
            raise ConnectionClosedError(None, None)
        except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
            raise

    async def handler(self, websocket):
        if len(self.CONNECTIONS) > 0:
            await websocket.send("Only one connection allowed at a time")
            await websocket.close()
            print("Only one connection allowed at a time")
            return
        else:
            self.CONNECTIONS.add(websocket)
        task1 = self.loop.create_task(self.consumer_handler(websocket))
        task2 = self.loop.create_task(self.producer_handler(websocket))
        try:
            await task1
            await task2
        except (ConnectionClosedOK, ConnectionClosedError, asyncio.CancelledError, Exception):
            print("HANDLER ERROR")
            task1.cancel()
            task2.cancel()
            self.stop_motors()
            self.CONNECTIONS.remove(websocket)
            try:
                await task1
            except Exception:
                pass
            try:
                await task2
            except Exception:
                pass

    async def handle_webserver(self):
        try:
            server = await serve(self.handler, "192.168.0.27", 8765)
            await server.serve_forever()
        except asyncio.CancelledError:
            server.close()
            await server.wait_closed()
            self.stop_motors()
            await self.connection.close()
            print("Connection closed and flushed")

    async def handle_board(self):
        try:
            print("HANDLE BOARD")
            t0 = time()
            q0 = t0
            while True:
                t1 = time()
                dt = t1-t0
                t0 = t1
                RATE = self.SETTINGS["Max Acceleration"] if (abs(self.CURRENT) < abs(self.TARGET)) else self.SETTINGS["Max Deceleration"]
                if self.CURRENT < self.TARGET:
                    self.CURRENT = min(self.CURRENT + dt*RATE, self.TARGET)
                elif self.CURRENT > self.TARGET:
                    self.CURRENT = max(self.CURRENT - dt*RATE, self.TARGET)
                if abs(self.CURRENT) < 100:
                    self.write_both(SetCurrent(0))
                else:
                    self.write_both(SetRPM(int(self.CURRENT)))
                for con in self.CONNECTIONS:
                    if con.open:
                        if t1-q0 > 0.1:
                            self.write_both(GetValues())
                            q0 = t1
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            print("Board Handler Closed")
        except Exception as e:
            print(e)

server = Server()
server.start()