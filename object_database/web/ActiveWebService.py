#   Copyright 2018 Braxton Mckee
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import traceback
import threading
import logging
import time
import uuid
import base64
import json
import sys
import time
import argparse
import os.path
import logging
import traceback
import datetime
import os
import json
from gevent import pywsgi
from geventwebsocket.handler import WebSocketHandler

from object_database.web.cells import *

from gevent.greenlet import Greenlet
from gevent import sleep

from flask import Flask, send_from_directory, redirect, url_for
from flask_sockets import Sockets

from object_database import ServiceBase, service_schema, Schema, Indexed, Index

active_webservice_schema = Schema("core.active_webservice")

@active_webservice_schema.define
class Configuration:
    service = Indexed(service_schema.Service)

    port = int
    hostname = str

class ActiveWebService(ServiceBase):
    def __init__(self, db, serviceInstance):
        ServiceBase.__init__(self, db, serviceInstance)

    @staticmethod
    def configureFromCommandline(db, serviceObject, args):
        """Subclasses should take the remaining args from the commandline and configure using them"""
        db.subscribeToType(Configuration)

        with db.transaction():
            c = Configuration.lookupAny(service=serviceObject)
            if not c:
                c = Configuration(service=serviceObject)

            parser = argparse.ArgumentParser("Configure a webservice")
            parser.add_argument("--hostname", type=str)
            parser.add_argument("--port", type=int)

            parsedArgs = parser.parse_args(args)

            c.port = parsedArgs.port
            c.hostname = parsedArgs.hostname

    def initialize(self):
        self.db.subscribeToType(Configuration)

        with self.db.transaction():
            self.app = Flask(__name__)
            self.sockets = Sockets(self.app)
            self.configureApp()

    def doWork(self, shouldStop):
        logging.info("Configuring ActiveWebService")
        with self.db.view():
            config = Configuration.lookupAny(service=self.serviceInstance.service)
            assert config, "No configuration available."
            host,port = config.hostname, config.port

        server = pywsgi.WSGIServer((host, port), self.app, handler_class=WebSocketHandler)

        server.serve_forever()
    
    def configureApp(self):
        self.app.route('/content/<path:path>')(self.sendContent)
        self.sockets.route("/echo")(self.echoSocket)
        self.sockets.route("/socket")(self.mainSocket)
        self.sockets.route("/")(lambda: redirect(url_for("content/page.html")))
        
    def createCells(self):
        cells = Cells(self.db)

        curService = Slot(None)

        def serviceCountSetter(service, ct):
            def f():
                print("Setting service ", service, " with tgc ", service.target_count, " to ", ct)
                service.target_count = ct
            return f

        serviceGrid = Grid(
                colFun=lambda: ['Service', 'Codebase', 'Module', 'Class', 'Placement', 'Active', 'TargetCount', 'Cores', 'RAM'],
                rowFun=lambda: sorted(service_schema.Service.lookupAll(), key=lambda s:s.name),
                headerFun=lambda x: x,
                rowLabelFun=lambda s: Subscribed(lambda: s.name),
                rendererFun=lambda s,field: Subscribed(lambda: 
                    s.name if field == 'Service' else
                    (str(s.codebase) if s.codebase else "") if field == 'Codebase' else
                    s.service_module_name if field == 'Module' else
                    s.service_class_name if field == 'Class' else 
                    s.placement if field == 'Placement' else 
                    Subscribed(lambda: len(service_schema.ServiceInstance.lookupAll(service=s))) if field == 'Active' else
                    Span(s.target_count) + 
                        Dropdown("ct", [(str(ct), serviceCountSetter(s, ct)) for ct in range(10)]) 
                            if field == 'TargetCount' else 
                    str(s.coresUsed) if field == 'Cores' else 
                    str(s.gbRamUsed) if field == 'RAM' else 
                    ""
                    )
                )
        
        def displayForService(serviceObj):
            return serviceObj.instantiateServiceObject().serviceDisplay(serviceObj)
            

        cells.root.setChild(
            HeaderBar(
                [Subscribed(lambda: 
                    Dropdown(
                        "Service",
                            [("All", lambda: curService.set(None))] + 
                            [(s.name, lambda: curService.set(s)) for 
                                s in sorted(service_schema.Service.lookupAll(), key=lambda s:s.name)]
                        ),
                    )
                ]) +
            Main(
                Subscribed(lambda:
                    serviceGrid if curService.get() is None else
                        displayForService(curService.get())
                    )
                )
            )

        return cells

    def mainSocket(self, ws):
        reader = None

        try:
            logging.info("Starting main websocket handler with %s", ws)

            cells = self.createCells()

            timestamps = []

            def readThread():
                while not ws.closed:
                    msg = ws.receive()
                    if msg is None:
                        return
                    else:
                        try:
                            jsonMsg = json.loads(msg)

                            cell_id = jsonMsg.get('target_cell')
                            cell = cells.cells.get(cell_id)
                            if cell is not None:
                                cell.onMessage(jsonMsg)
                        except:
                            logging.error("Exception in inbound message: %s", traceback.format_exc())
                        cells.triggerIfHasDirty()

            reader = Greenlet.spawn(readThread)

            while not ws.closed:
                t0 = time.time()
                cells.recalculate()
                
                for message in reversed(cells.renderMessages()): 
                    ws.send(json.dumps(message))
                
                cells.gEventHasTransactions.wait()

                timestamps.append(time.time())

                if len(timestamps) > MAX_FPS:
                    timestamps = timestamps[-MAX_FPS+1:]
                    if (time.time() - timestamps[0]) < 1.0:
                        sleep(1.0 / MAX_FPS + .001)

        except:
            logging.error("Websocket handler error: %s", traceback.format_exc())
        finally:
            if reader:
                reader.join()

    def echoSocket(self, ws):
        while not ws.closed:
            message = ws.receive()
            if message is not None:
                ws.send(message)
            
    def sendContent(self, path):
        own_dir = os.path.dirname(__file__)
        return send_from_directory(os.path.join(own_dir, "content"), path)

    @staticmethod
    def serviceDisplay(serviceObject):
        c = Configuration.lookupAny(service=serviceObject)

        return Card(Text("Host: " + c.hostname) + Text("Port: " + str(c.port)))
