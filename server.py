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

class Server:
    def __init__(self):
        self.can_id = 124
        self.CONNECTIONS = set()
        self.CURRENT = 0
        self.TARGET = 0
        self.VALUE_DATA = GetValues()
        self.ACC_RPM_PER_SECOND = 5000
        self.DEC_RPM_PER_SECOND = 15000

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
        #self.CURRENT = 0
        #self.write_both(SetCurrent(0))

    async def parse_command(self, websocket, id, fields):
        try:
            if id == "setTarget":
                self.TARGET = fields['target']
            elif id == "getTarget":
                await websocket.send(json.dumps({'id': id, 'fields': {'target': self.TARGET}}))
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
                        print("Connection Failure")
                except Exception:
                    print("Connection Failure")
            print("CONSUMER DONE")
            raise ConnectionClosedError(None, None)
        except (asyncio.CancelledError, ConnectionClosedError, ConnectionClosedOK):
            raise


    async def producer_handler(self, websocket):
        try:
            count = 0
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
        count = 0
        try:
            print("HANDLE BOARD")
            t0 = time()
            while True:
                t1 = time()
                dt = t1-t0
                t0 = t1
                if self.CURRENT < self.TARGET:
                    self.CURRENT = min(self.CURRENT + dt*self.ACC_RPM_PER_SECOND, self.TARGET)
                elif self.CURRENT > self.TARGET:
                    self.CURRENT = max(self.CURRENT - dt*self.DEC_RPM_PER_SECOND, self.TARGET)
                if abs(self.CURRENT) < 100:
                    self.write_both(SetCurrent(0))
                else:
                    self.write_both(SetRPM(int(self.CURRENT)))
                for con in self.CONNECTIONS:
                    if con.open:
                        self.write_both(GetValues())
                await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            print("Board Handler Closed")
        except Exception as e:
            print(e)

server = Server()
server.start()