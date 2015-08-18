# Copyright 2015 StackHut Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
import threading
import sys
import os
import json
from queue import Queue
import urllib.parse
import requests
from stackhut_common.utils import log, DEBUG

# names to export
__all__ = ['stackhut_api_call', 'stackhut_api_user_call', 'keen_client', 'get_res_path']

# Setup app paths
sys_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(__file__)
res_dir = os.path.normpath(os.path.join(sys_dir, './res'))

def get_res_path(res_name):
    return os.path.join(res_dir, res_name)

###################################################################################################
# StackHut server comms
json_header = {'content-type': 'application/json'}

def secure_url_prefix():
    return "http://{}/".format(DEBUG) if DEBUG is not None else "https://api.stackhut.com/"

def unsecure_url_prefix():
    return "http://{}/".format(DEBUG) if DEBUG is not None else "http://api.stackhut.com/"

def stackhut_api_call(endpoint, msg, secure=True):
    url_prefix = secure_url_prefix() if secure else unsecure_url_prefix()
    log.debug(url_prefix)
    url = urllib.parse.urljoin(url_prefix, endpoint)
    log.debug("Calling Stackhut Server {} with \n\t{}".format(endpoint, json.dumps(msg)))
    r = requests.post(url, data=json.dumps(msg), headers=json_header)

    if r.status_code == requests.codes.ok:
        return r.json()
    else:
        log.error("Error {} talking to Stackhut Server".format(r.status_code))
        log.error(r.text)
        r.raise_for_status()

def stackhut_api_user_call(endpoint, data, usercfg):
    auth = dict(username=usercfg.username, hash=usercfg['hash'])
    message = dict(auth=auth, data=data)
    return stackhut_api_call(endpoint, message)



###################################################################################################
# Keen analytlics
class KeenClient(threading.Thread):
    project_id = '559f866f96773d25d47419f6'
    write_key = 'abd65ad8684753678eabab1f1c536b36a70704e6c4f10bcfe928c10ec859edb1d0366f3fad9b7794b0' \
                'eeab9825a27346e0186e2e062f76079708b66ddfca7ecc82b8db23062f8cd2e4f6a961d8d2ea23b22f' \
                'c9aae1387514da6d46cdbebec2d15c9167d401963ee8f96b00e06acf4e48'
    keen_url = "https://api.keen.io/3.0/projects/{project_id}/events/{{event_collection}}?" \
               "api_key={write_key}".format(project_id=project_id, write_key=write_key)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.send_analytics = False
        self.analytics_ids = None
        self.queue = Queue()

    def start(self, usercfg):
        self.send_analytics = usercfg.send_analytics
        if self.send_analytics:
            log.debug("User analytics enabled")
            self.analytics_ids = usercfg.analytics_ids
            super().start()
        else:
            log.debug("User analytics disabled")

    def run(self):
        while True:
            (endpoint, msg) = self.queue.get()
            msg.update(self.analytics_ids)
            try:
                log.debug("Sending analytics msg to {}".format(endpoint))
                log.debug("Analytics msg - {}".format(msg))
                url = self.keen_url.format(event_collection=endpoint)
                r = requests.post(url, data=json.dumps(msg), headers=json_header, timeout=2)
                if not (r.status_code == requests.codes.created and r.json().get('created')):
                    log.debug("{} - {}".format(r.status_code, r.text()))
                    raise IOError()
            except:
                log.debug("Failed sending analytics msg to '{}'".format(endpoint))
            finally:
                self.queue.task_done()

    def send(self, endpoint, msg):
        if self.send_analytics:
            self.queue.put((endpoint, msg))

    def shutdown(self):
        if self.send_analytics:
            self.queue.join()

keen_client = KeenClient(daemon=True)