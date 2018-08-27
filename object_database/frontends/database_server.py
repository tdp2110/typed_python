#!/usr/bin/env python3

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

import argparse
import sys
import time
import typed_python
import object_database.tcp_server as tcp_server
from object_database.persistence import InMemoryStringStore, RedisStringStore

def main(argv):
    parser = argparse.ArgumentParser("Run an object_database server")

    parser.add_argument("host")
    parser.add_argument("port", type=int)
    parser.add_argument("--redis_port", type=int, default=None)
    parser.add_argument("--inmem", default=False, action='store_true')

    parsedArgs = parser.parse_args(argv[1:])

    if parsedArgs.inmem:
        mem_store = InMemoryStringStore()
    else:
        mem_store = RedisStringStore(port=parsedArgs.redis_port)

    databaseServer = tcp_server.TcpServer(parsedArgs.host, parsedArgs.port, mem_store)

    databaseServer.start()

    try:
    	while True:
    		time.sleep(0.1)
    except KeyboardInterrupt:
    	return

if __name__ == '__main__':
    main(sys.argv)