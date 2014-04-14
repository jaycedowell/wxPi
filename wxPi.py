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
import signal
import logging
import logging.handlers
import threading

from config import CONFIG_FILE, loadConfig
from database import Archive
from decoder import read433
from parser import parsePacketStream
from utils import computeDewPoint, computeSeaLevelPressure, wuUploader

from sensors.bmpBackend import BMP085
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

	try:
		opts, args = getopt.getopt(args, "hc:p:d", ["help", "config-file=", "pid-file=", "debug"])
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
		else:
			assert False
	
	# Add in arguments
	config['args'] = args

	# Parse the configuration file
	cFile = loadConfig(config['configFile'])
	for k,v in cFile.iteritems():
		config[k] = v

	# Return configuration
	return config


def main(args):
	# Parse the command line and read in the configuration file
	config = parseOptions(args)
	
	# Setup the logging
	## Basic
	logger = logging.getLogger(__name__)
	if config['debug']:
		logger.setLevel(logging.DEBUG)
	else:
		logger.setLevel(logging.INFO)
	## Handler
	handler = logging.handlers.SysLogHandler(address='/dev/log')
	logger.addHandler(handler)
	## Format
	format = formatter = logging.Formatter(os.path.basename(__file__)+'[%(process)d]: %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
	handler.setFormatter(format)
	
	# PID file
	if config['pidFile'] is not None:
		fh = open(config['pidFile'], 'w')
		fh.write("%i\n" % os.getpid())
		fh.close()
	logger.info('Starting wxPi.py')
	
	# Setup a flag that we can toggle if we receive a signal
	alive = threading.Event()
	alive.set()
	
	# Setup handler for SIGTERM so that we aren't left in a funny state
	def HandleSignalExit(signum, loopflag=alive, logger=logger):
		logger.info('Exiting on signal %i', signum)
		
		# Stop the loop
		loopflag.clear()
		
	# Hook in the signal handler - SIGINT SIGTERM SIGQUIT SIGPIPE
	signal.signal(signal.SIGINT,  HandleSignalExit)
	signal.signal(signal.SIGTERM, HandleSignalExit)
	signal.signal(signal.SIGQUIT, HandleSignalExit)
	signal.signal(signal.SIGPIPE, HandleSignalExit)
	
	# Get the latest from the database
	try:
		db = Archive()
		tData, sensorData = db.getData()
		if time.time() - tData > 2*config['duration']:
			sensorData = {}
			
	except RuntimeError, e:
		db = None
		tData, sensorData = time.time(), {}
		logging.error(str(e))
		
	# Make sure the database has provided something useful.  If not, we need to
	# run several iterations to build up the current picture of what is going on.
	if len(sensorData.keys()) == 0:
		buildState = True
		loopsForState = 3
	else:
		buildState = False
		loopsForState = 1
		
	# Enter the main loop
	tLastUpdate = 0.0
	while alive.isSet():
		## Begin the loop
		t0 = time.time()
		
		## Read from the 433 MHz radio
		for i in xrange(loopsForState):
			config['red'].on()
			tData = time.time() + int(round(config['duration']*0.75))/2.0
			packets = read433(config['radioPin'], int(round(config['duration']*0.75)))
			config['red'].off()
		
			## Process the received packets and update the internal state
			config['yellow'].on()
			sensorData = parsePacketStream(packets, elevation=config['elevation'], 
											inputDataDict=sensorData)
			config['yellow'].off()
		
			# Poll the BMP085/180 - if needed
			if config['enableBMP085']:
				config['red'].on()
				ps = BMP085(address=0x77, mode=3)
				pressure = ps.readPressure() / 100.0
				temperature = ps.readTemperature()
				config['red'].off()
			
				config['yellow'].on()
				sensorData['pressure'] =  pressure
				sensorData['pressure'] = computeSeaLevelPressure(sensorData['pressure'], config['elevation'])
				if 'indoorHumidity' in sensorData.keys():
					sensorData['indoorTemperature'] = ps.readTemperature()
					sensorData['indoorDewpoint'] = computeDewPoint(sensorData['indoorTemperature'], sensorData['indoorHumidity'])
				config['yellow'].off()
				
		## Have we built up the state?
		if buildState:
			loopsForState = 1
			
		## Check if there is anything to update in the archive
		config['yellow'].on()
		if tData != tLastUpdate:
			db.writeData(tData, sensorData)
			logger.info('Saving current state to archive')
		else:
			logger.warning('Data timestamp has not changed since last poll, archiving skipped')
		config['yellow'].off()
		
		## Post the results to WUnderground
		if tData != tLastUpdate:
			uploadStatus = wuUploader(config['ID'], config['PASSWORD'], 
										tData, sensorData, archive=db, 
										includeIndoor=config['includeIndoor'])
										
			if uploadStatus:
				tLastUpdate = 1.0*tData
				
				logger.info('Posted data to WUnderground')
				config['green'].blink()
				time.sleep(3)
				config['green'].blink()
			else:
				logger.error('Failed to post data to WUnderground')
				config['red'].blink()
				time.sleep(3)
				config['red'].blink()
				
		else:
			logger.warning('Data timestamp has not changed since last poll, archiving skipped')
			
		## Done
		t1 = time.time()
		tSleep = config['duration'] - (t1-t0)
		tSleep = tSleep if tSleep > 0 else 0
		
		## Sleep
		time.sleep(tSleep)
		
	# Stop the logger
	logger.info('Finished')	
	logging.shutdown()


if __name__ == "__main__":
	daemonize('/dev/null', '/dev/null', '/tmp/wxPi.stderr')
	main(sys.argv[1:])
	
