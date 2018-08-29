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


from object_database.service_manager.ServiceManager import ServiceManager
from object_database.service_manager.ServiceWorker import ServiceWorker
from object_database.service_manager.ServiceManagerSchema import service_schema
from object_database import connect

import threading
import time
import logging
import sys
import subprocess
import os
import shutil

ownDir = os.path.dirname(os.path.abspath(__file__))

def timestampToFileString(timestamp):
    struct = time.localtime(timestamp)
    return "%4d%02d%02d_%02d%02d%02d_%03d" % (
        struct.tm_year,
        struct.tm_mon,
        struct.tm_mday,
        struct.tm_hour,
        struct.tm_min,
        struct.tm_sec,
        int(timestamp*1000) % 1000
        )

def parseLogfileToInstanceid(fname):
    if not fname.endswith(".log.txt") or "-" not in fname:
        return
    return fname.split("-")[-1][:-8]

class SubprocessServiceManager(ServiceManager):
    def __init__(self, own_hostname, host, port, isMaster, maxGbRam=4, maxCores=4, logfileDirectory=None, shutdownTimeout=None):
        self.own_hostname = own_hostname
        self.host = host
        self.port = port
        self.logfileDirectory = logfileDirectory
        self.lock = threading.Lock()

        if logfileDirectory is not None:
            if not os.path.exists(logfileDirectory):
                os.makedirs(logfileDirectory)

        def dbConnectionFactory():
            return connect(host, port)

        ServiceManager.__init__(self, dbConnectionFactory, isMaster, own_hostname, maxGbRam=maxGbRam, maxCores=maxCores, shutdownTimeout=shutdownTimeout)

        self.serviceProcesses = {}

    def _startServiceWorker(self, service, instanceIdentity):
        if instanceIdentity in self.serviceProcesses:
            return

        with self.lock:
            logfileName = service.name + "-" + timestampToFileString(time.time()) + "-" + instanceIdentity + ".log.txt"

            if self.logfileDirectory is not None:
                output_file = open(os.path.join(self.logfileDirectory, logfileName), "w")
            else:
                output_file = None
            
            process = subprocess.Popen(
                [sys.executable, os.path.join(ownDir, '..', 'frontends', 'service_entrypoint.py'),
                 self.host, str(self.port), instanceIdentity],
                stdin=subprocess.DEVNULL,
                stdout=output_file,
                stderr=subprocess.STDOUT
                )

            self.serviceProcesses[instanceIdentity] = process

            if output_file:
                output_file.close()

        if self.logfileDirectory:
            logging.info(
                "Started a service logging to %s with pid %s",
                os.path.join(self.logfileDirectory, logfileName),
                process.pid
                )
        else:
            logging.info(
                "Started service %s/%s with pid %s",
                service.name,
                instanceIdentity,
                process.pid
                )

    def stop(self):
        self.stopAllServices(self.shutdownTimeout)

        for instanceIdentity, workerProcess in self.serviceProcesses.items():
            workerProcess.terminate()
            workerProcess.wait()

        self.serviceProcesses = {}

        ServiceManager.stop(self)

    def cleanup(self):
        for identity, workerProcess in list(self.serviceProcesses.items()):
            if workerProcess.poll() is not None:
                workerProcess.wait()
                del self.serviceProcesses[identity]

        with self.db.view():
            for identity in list(self.serviceProcesses):
                serviceInstance = service_schema.ServiceInstance.fromIdentity(identity)

                if serviceInstance.shouldShutdown and time.time() - serviceInstance.shutdownTimestamp > self.shutdownTimeout:
                    workerProcess = self.serviceProcesses.get(identity)
                    if workerProcess:
                        workerProcess.terminate()
                        workerProcess.wait()
                        del self.serviceProcesses[identity]

        self.cleanupOldLogfiles()

    def cleanupOldLogfiles(self):
        if self.logfileDirectory:
            with self.lock:
                for file in os.listdir(self.logfileDirectory):
                    instanceId = parseLogfileToInstanceid(file)
                    if instanceId and instanceId not in self.serviceProcesses:
                        if not os.path.exists(os.path.join(self.logfileDirectory, "old")):
                            os.makedirs(os.path.join(self.logfileDirectory, "old"))
                        shutil.move(os.path.join(self.logfileDirectory, file), os.path.join(self.logfileDirectory, "old", file))



