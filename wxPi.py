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
import logging
import logging.handlers

from config import CONFIG_FILE, loadConfig
from database import Archive
from decoder import read433
from parser import parsePacketStream
from utils import computeDewPoint, computeSeaLevelPressure, generateWeatherReport, wuUploader

from led import on as ledOn, off as ledOff, blinkOn, blinkOff
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


def main(args):
	# Read in the configuration file
	config = loadConfig(CONFIG_FILE)
	
	# Setup the logging
	logger = logging.getLogger(__main__)
	logger.setLevel(logging.INFO)
	
	handler = logging.handlers.SysLogHandler(address = '/dev/log')
	logger.addHandler(handler)
	
	# Open the database and read in the most recent state.  If the database doesn't exist
	# or the state is stale we need to poll the 
	try:
		db = Archive()
		tData, sensorData = db.getData()
		if time.time() - tData > 2*config['duration']:
			sensorData = {}
			
	except RuntimeError, e:
		db = None
		tData, sensorData = time.time(), {}
		
		print "WARNING: %s" % str(e)
		
	clearToSend = True
	if len(sensorData.keys()) == 0:
		clearToSend = False
		
	# Enter the main loop
	pollCounter = 0
	while True:
		# Begin the loop
		t0 = time.time()
		
		# Record some data and extract the bits on-the-fly
		ledOn(config['redPin'])
		tData = time.time() + config'duration'])/2
		packets = read433(config['radioPin'], int(config['duration'])/2, verbose=config['verbose'])
		ledOff(config['redPin'])
		
		# Find the packets and save the output
		ledOn(config['yellowPin'])
		sensorData = parsePacketStream(packets, elevation=config['elevation'], inputDataDict=sensorData, verbose=config['verbose'])
		ledOff(config['yellowPin'])	
		
		# Poll the BMP085/180 for pressure and indoor temperature
		if config['enableBMP085']:
			ledOn(config['redPin'])
			ps = BMP085(address=0x77, mode=3)
			sensorData['pressure'] = ps.readPressure() / 100.0 
			sensorData['pressure'] = computeSeaLevelPressure(sensorData['pressure'], config['elevation'])
			if 'indoorHumidity' in sensorData.keys():
				sensorData['indoorTemperature'] = ps.readTemperature()
				sensorData['indoorDewpoint'] = computeDewPoint(sensorData['indoorTemperature'], sensorData['indoorHumidity'])
			ledOff(config['redPin'])
	
		# Save to the database
		ledOn(config['yellowPin'])
		if db is not None:
			if clearToSend:
				db.writeData(tData, sensorData)
			
		# Upload
		if clearToSend:
			uploadStatus = wuUploader(config['ID'], config['PASSWORD'], tData, sensorData, archive=db, 
										includeIndoor=config['includeIndoor'], verbose=config['verbose'])
			ledOff(config['yellowPin'])
	
			# Report status of upload...
			if uploadStatus:
				ledColor = config['greenPin']
				logger.info('Posted weather data to WUnderground')
			else:
				ledColor = config['redPin']
				logger.error('Failed to post weather data to WUnderground')
			# ... with an LED
			blinkOn(ledColor)
			time.sleep(3)
			blinkOff(ledColor)
			ledOff(ledColor)
			
		# Check the clearToSend state
		if not clearToSend:
			if pollCounter > 3 and len(sensorData.keys()) > 0:
				clearToSend = True
				
		# End the loop and sleep
		t1 = time.time()
		tSleep = config['duration'] - (t1-t0)
		time.sleep(tSleep)
		
		pollCounter += 1


if __name__ == "__main__":
	daemonize('/dev/null','/tmp/wxPi.stdout','/tmp/wxPi.stderr')
	main(sys.argv[1:])
	