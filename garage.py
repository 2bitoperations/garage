__author__ = 'armalota'
import json
import urllib2
import time
from flask import Flask, Response, request
from functools import wraps
from flask import json
import threading
import logging
from Adafruit_BMP085 import BMP085
import sys
import signal
import RPi.GPIO as GPIO
import time

# active low relays from amazon here: http://www.amazon.com/gp/product/B00C59NOHK/ref=wms_ohs_product?ie=UTF8&psc=1
# reed switch door state sensors from here: http://www.amazon.com/gp/product/B0050N7SM0/ref=wms_ohs_product?ie=UTF8&psc=1

BAYS = [{'sense': 25, 'relay': 22}, {'sense': 24, 'relay': 23}]

app = Flask(__name__)
rootLogger = logging.getLogger()
rootLogger.setLevel(logging.DEBUG)

ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
rootLogger.addHandler(ch)

#fileLogger = logging.FileHandler("/tmp/server.log")
#fileLogger.setLevel(logging.DEBUG)
#fileLogger.setFormatter(formatter)
#rootLogger.addHandler(fileLogger)

def check_auth(username, password):
    return username == 'armalota' and password=='some super secret password'

def authenticate():
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@app.route("/bay/<int:bay_id>", methods=['PUT'])
@requires_auth
def click_bay(bay_id):
    GPIO.output(BAYS[bay_id]['relay'], False)
    time.sleep(.5)
    GPIO.output(BAYS[bay_id]['relay'], True)
    return bay_status()

@app.route("/bays", methods=['GET'])
@requires_auth
def bay_status():
    bays = dict()
    bays['bay0'] = GPIO.input(BAYS[0]['sense']) == 0
    bays['bay1'] = GPIO.input(BAYS[1]['sense']) == 0
    return json.dumps(bays)

class Ingester:
    def __init__(self):
        self.stopRequested = False
        self.bmp = BMP085(0x77, 3)
        self.logger = logging.getLogger('ingester')

    def go(self):
        while not self.stopRequested:
            temp = self.bmp.readTemperature()
            pressure = self.bmp.readPressure() / 100.0

            out = dict()
            out['temp'] = temp
            out['pressure'] = pressure

            try:
                opener = urllib2.build_opener(urllib2.HTTPHandler)
                request = urllib2.Request('http://192.168.5.1:8088/wx/garage/current', data=json.dumps(out))
                request.add_header('Content-Type', 'application/json')
                request.get_method = lambda: 'PUT'
                opener.open(request)
                self.logger.debug(json.dumps(out))
                time.sleep(2)
            except Exception as e:
                self.logger.error(e)

class SigHandler:
    def __init__(self, ingest_thread):
        self.ingest_thread = ingest_thread
        self.stopRequested = False

    def handle_ctrlc(self, signal, frame):
        self.ingest_thread.stopRequested = True
        self.stopRequested = True
        sys.exit(0)

GPIO.setmode(GPIO.BCM)
for bay in BAYS:
    GPIO.setup(bay['relay'], GPIO.OUT)
    GPIO.output(bay['relay'], True)
    GPIO.setup(bay['sense'], GPIO.IN)

global ingest
ingest = Ingester.getInstance()
ingest_thread = threading.Thread(target=ingest.go)
ingest_thread.start()
logging.warn("ingest started.")

signal_handler = SigHandler(ingest)
signal.signal(signal.SIGINT, signal_handler.handle_ctrlc)
logging.warn("sighandler started.")
