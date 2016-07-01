#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script to record 433MHz dat in search of packets from Oregon Scientific 
weather sensors and a BMP085/180, and send the results to WUnderground.

This script takes no arguments.
"""

import os
import sys
import time
import getopt
import calendar
from datetime import datetime

import jinja2
import cherrypy
from cherrypy.process.plugins import Daemonizer

import logging
try:
	from logging.handlers import WatchedFileHandler
except ImportError:
	from logging import FileHandler as WatchedFileHandler

from config import *
from database import Archive
from polling import PollingProcessor
from utils import temp_C2F, pressure_mb2inHg, speed_ms2mph, length_mm2in

# Path configuration
_BASE_PATH = os.path.dirname(os.path.abspath(__file__))
CSS_PATH = os.path.join(_BASE_PATH, 'css')
JS_PATH = os.path.join(_BASE_PATH, 'js')
TEMPLATE_PATH = os.path.join(_BASE_PATH, 'templates')


# Jinja configuration
jinjaEnv = jinja2.Environment(loader=jinja2.FileSystemLoader(TEMPLATE_PATH), 
							  extensions=['jinja2.ext.loopcontrols',])


"""
This module is used to fork the current process into a daemon.
Almost none of this is necessary (or advisable) if your daemon
is being started by inetd. In that case, stdin, stdout and stderr are
all set up for you to refer to the network connection, and the fork()s
and session manipulation should not be done (to avoid confusing inetd).
Only the chdir() and umask() steps remain as useful.

From:
  http://code.activestate.com/recipes/66012-fork-a-daemon-process-on-unix/

References:
  UNIX Programming FAQ
    1.7 How do I get my program to act like a daemon?
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        
    Advanced Programming in the Unix Environment
      W. Richard Stevens, 1992, Addison-Wesley, ISBN 0-201-56317-7.
"""

def daemonize(stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
	"""
	This forks the current process into a daemon.
	The stdin, stdout, and stderr arguments are file names that
	will be opened and be used to replace the standard file descriptors
	in sys.stdin, sys.stdout, and sys.stderr.
	These arguments are optional and default to /dev/null.
	Note that stderr is opened unbuffered, so
	if it shares a file with stdout then interleaved output
	may not appear in the order that you expect.
	"""
	
	# Do first fork.
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0) # Exit first parent.
	except OSError, e:
		sys.stderr.write("fork #1 failed: (%d) %s\n" % (e.errno, e.strerror))
		sys.exit(1)
		
	# Decouple from parent environment.
	os.chdir("/")
	os.umask(0)
	os.setsid()
	
	# Do second fork.
	try:
		pid = os.fork()
		if pid > 0:
			sys.exit(0) # Exit second parent.
	except OSError, e:
		sys.stderr.write("fork #2 failed: (%d) %s\n" % (e.errno, e.strerror))
		sys.exit(1)
		
	# Now I am a daemon!
	
	# Redirect standard file descriptors.
	si = file(stdin, 'r')
	so = file(stdout, 'a+')
	se = file(stderr, 'a+', 0)
	os.dup2(si.fileno(), sys.stdin.fileno())
	os.dup2(so.fileno(), sys.stdout.fileno())
	os.dup2(se.fileno(), sys.stderr.fileno())


def usage(exitCode=None):
	print """wxPi.py Read data from a v2 Oregon Scientific weather station and post the
data to WUnderground.

Usage: wxPi.py [OPTIONS]

Options:
-h, --help                  Display this help information
-c, --config-file           Path to configuration file
-p, --pid-file              File to write the current PID to
-d, --debug                 Set the logging to 'debug' level
-l, --logfile               Set the logfile (default = /var/log/wxpi
"""

	if exitCode is not None:
		sys.exit(exitCode)
	else:
		return True


def parseOptions(args):
	config = {}
	config['configFile'] = CONFIG_FILE
	config['pidFile'] = None
	config['debug'] = False
	config['logfile'] = '/var/log/wxpi'

	try:
		opts, args = getopt.getopt(args, "hc:p:dl:", ["help", "config-file=", "pid-file=", "debug", "logfile="])
	except getopt.GetoptError, err:
		# Print help information and exit:
		print str(err) # will print something like "option -a not recognized"
		usage(exitCode=2)
	
	# Work through opts
	for opt, value in opts:
		if opt in ('-h', '--help'):
			usage(exitCode=0)
		elif opt in ('-c', '--config-file'):
			config['configFile'] = str(value)
		elif opt in ('-p', '--pid-file'):
			config['pidFile'] = str(value)
		elif opt in ('-d', '--debug'):
			config['debug'] = True
		elif opt in ('-l', '--logfile'):
			config['logfile'] = value
		else:
			assert False
	
	# Add in arguments
	config['args'] = args
	
	# Return configuration
	return config


# AJAX interface
class AJAX(object):
	def __init__(self, config, db, leds):
		self.config = config
		self.db = db
		self.leds = leds
		
	def serialize(self, dt):
		if isinstance(dt, datetime):
			if dt.utcoffset() is not None:
				dt = dt - dt.utcoffset()
		millis = int(calendar.timegm(dt.timetuple()) * 1000 + dt.microsecond / 1000)
		return millis
    	
	@cherrypy.expose
	@cherrypy.tools.json_out()
	def summary(self):
		## Query
		ts, output = self.db.getData()
		
		### Ouch... there has to be a better way to do this
		tUTCMidnight = (int(time.time()) / 86400) * 86400
		localOffset = int(round(float(datetime.utcnow().strftime("%s.%f")) - time.time(), 1))
		tLocalMidnight = tUTCMidnight + localOffset
		if tLocalMidnight > time.time():
			tLocalMidnight -= 86400
			
		### Get the rainfall from an hour ago, from local midnight, and year-to-date
		jk, entry = self.db.getData(age=3630)
		rainHour = entry['rainfall']
		jk, entry  = self.db.getData(age=time.time()-tLocalMidnight+30)
		rainDay = entry['rainfall']
		jk, entry = self.db.getDataYearStart()
		rainYear = entry['rainfall']
		
		## Cleanup
		for key in ('temperature', 'windchill', 'dewpoint', 'indoorTemperature', 'indoorDewpoint'):
			try:
				output[key] = temp_C2F( output[key] )
			except KeyError:
				pass
		for key in ('average', 'gust'):
			try:
				output[key] = speed_ms2mph( output[key] )
			except KeyError:
				pass
		for key in ('rainrate', 'rainfall'):
			try:
				output[key] = length_mm2in( output[key] )
			except KeyError:
				pass
		output['pressure'] = pressure_mb2inHg( output['pressure'] )
		
		## Computed rain quantities
		if rainHour >= 0:
			try:
				output['rainfallHour'] = output['rainfall'] - length_mm2in( rainHour )
				if output['rainfallHour'] < 0:
					output['rainfallHour'] = 0.0
			except KeyError:
				pass
		if rainDay >= 0:
			try:
				output['rainfallDay']  = output['rainfall'] - length_mm2in( rainDay )
				if output['rainfallDay'] < 0:
					output['rainfallDay'] = 0.0
			except KeyError:
				pass
		if rainYear >= 0:
			try:
				output['rainfallYear'] = output['rainfall'] - length_mm2in( rainYear )
				if output['rainfallYear'] < 0:
					output['rainfallYear'] = 0.0
			except KeyError:
				pass
				
		## Timestamp
		output['timestamp'] = datetime.fromtimestamp(ts).strftime('%Y/%m/%d %H:%M:%S')
			
		## Done
		return output


# Main web interface
class Interface(object):
	def __init__(self, config, db, leds):
		self.config = config
		self.db = db
		self.leds = leds
		
		self.query = AJAX(config, db, leds)
		
	@cherrypy.expose
	def index(self):
		ts, kwds = self.db.getData()
		kwds['tNow'] = datetime.now()
		kwds['tzOffset'] = int(datetime.now().strftime("%s")) - int(datetime.utcnow().strftime("%s"))
		
		template = jinjaEnv.get_template('outdoor.html')
		return template.render({'kwds':kwds})
		
	@cherrypy.expose
	def indoor(self):
		ts, kwds = self.db.getData()
		kwds['tNow'] = datetime.now()
		kwds['tzOffset'] = int(datetime.now().strftime("%s")) - int(datetime.utcnow().strftime("%s"))
		
		template = jinjaEnv.get_template('indoor.html')
		return template.render({'kwds':kwds})
		
	@cherrypy.expose
	def configure(self, **kwds):
		if len(kwds) == 0:
			kwds = self.config.asDict()
		else:
			self.config.fromDict(kwds)
			saveConfig(CONFIG_FILE, self.config)
			
		template = jinjaEnv.get_template('config.html')
		return template.render({'kwds':kwds})		


def main(args):
	# Parse the command line and read in the configuration file
	cmdConfig = parseOptions(args)
	
	# Setup logging
	logger = logging.getLogger(__name__)
	logFormat = logging.Formatter('%(asctime)s [%(levelname)-8s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	logFormat.converter = time.gmtime
	logHandler = WatchedFileHandler(cmdConfig['logfile'])
	logHandler.setFormatter(logFormat)
	logger.addHandler(logHandler)
	if cmdConfig['debug']:
		logger.setLevel(logging.DEBUG)
	else:
		logger.setLevel(logging.INFO)
		
	# PID file
	if cmdConfig['pidFile'] is not None:
		fh = open(cmdConfig['pidFile'], 'w')
		fh.write("%i\n" % os.getpid())
		fh.close()
		
	# CherryPy configuration
	cherrypy.config.update({'server.socket_host': '0.0.0.0', 'environment': 'production'})
	cpConfig = {'/css': {'tools.staticdir.on': True,
						 'tools.staticdir.dir': CSS_PATH},
          		'/js':  {'tools.staticdir.on': True,
          				 'tools.staticdir.dir': JS_PATH}
          		}
				
	# Report on who we are
	logger.info('Starting wxPi.py with PID %i', os.getpid())
	logger.info('All dates and times are in UTC except where noted')
	
	# Load in the configuration
	config = loadConfig(cmdConfig['configFile'])
	
	# Get the latest from the database
	db = Archive()
	db.start()
	
	tData, sensorData = db.getData()
	if time.time() - tData > 2*config.getfloat('Station', 'duration'):
		sensorData = {}
		
	# Initialize the LEDs
	leds = initLEDs(config)
	
	# Make sure the database has provided something useful.  If not, we need to
	# run several iterations to build up the current picture of what is going on.
	if len(sensorData.keys()) == 0:
		buildState = True
		loopsForState = 3
	else:
		buildState = False
		loopsForState = 1
		
	# Start the sensor polling
	bg = PollingProcessor(config, db, leds, buildState=buildState, loopsForState=loopsForState, sensorData=sensorData)
	bg.start()
	
	# Initialize the web interface
	ws = Interface(config, db, leds)
	#cherrypy.quickstart(ws, config=cpConfig)
	cherrypy.tree.mount(ws, "/", config=cpConfig)
	cherrypy.engine.start()
	cherrypy.engine.block()
	
	# Shutdown process
	logger.info('Shutting down wxPi, please wait...')
	
	# Stop the polling thread
	bg.cancel()
	
	# Make sure the LEDs are off
	for color in leds.keys():
		leds[color].off()
		
	# Shutdown the archive
	db.cancel()


if __name__ == "__main__":
	try:
		os.unlink('/tmp/wxPi.stdout')
	except OSError:
		pass
	try:
		os.unlink('/tmp/wxPi.stderr')
	except OSError:
		pass
		
	daemonize('/dev/null', '/tmp/wxPi.stdout', '/tmp/wxPi.stderr')
	main(sys.argv[1:])
	