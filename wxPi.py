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
from wxThreads import *
from utils import initState, wuUploader

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
	
	# Initialize the internal data state
	db, state = initState(config)
	
	# Setup the various threads
	threads = []
	threads.append( RadioMonitor(config, state, db) )
	if config['enableBMP085']:
		threads.append( BMP085Monitor(config, state, db) )
		
	# Start the threads
	for t in threads:
		t.start()
		time.sleep(1)
		
	# Setup handler for SIGTERM so that we aren't left in a funny state
	def HandleSignalExit(signum, threads=threads, logger=logger):
		logger.info('Exiting on signal %i', signum)
		
		# Stop all threads
		for t in threads:
			t.stop()
			
	# Hook in the signal handler - SIGINT SIGTERM SIGQUIT SIGPIPE
	signal.signal(signal.SIGINT,  HandleSignalExit)
	signal.signal(signal.SIGTERM, HandleSignalExit)
	signal.signal(signal.SIGQUIT, HandleSignalExit)
	signal.signal(signal.SIGPIPE, HandleSignalExit)
	
	# Enter the main loop
	tLastUpdateA = 0.0
	tLastUpdateU = 0.0
	while True:
		## Begin the loop
		t0 = time.time()
		
		## Archive the current state
		state.lock()
		
		## Turn on the yellow LED
		config['yellow'].on()
		
		## Get the current state
		tData, sensorData = state.get()
		uCount = state.getUpdateCount()
		
		## Check if there is anything to update
		if tData != tLastUpdateA:
			if uCount > 10:
				db.writeData(tData, sensorData)
				tLastUpdateA = 1.0*tData
				
				logger.info('Saving current state to archive')
			else:
				logger.warning('Too few updates to save data to archive')
				
		## Turn off the yellow LED
		config['yellow'].off()
		
		## Release lock on the current state
		state.unlock()
		
		## Post the results to WUnderground
		tData, sensorData = db.getData()
		
		# Make sure that it is fresh so that we only send the latest and greatest
		if tData != tLastUpdateU:
			if uCount > 10:
				if time.time()-tData < config['duration']:
					uploadStatus = wuUploader(config['ID'], config['PASSWORD'], 
										tData, sensorData, archive=db, 
										includeIndoor=config['includeIndoor'])
									
					if uploadStatus:
						tLastUpdateU = 1.0*tData
					
						logger.info('Posted data to WUnderground')
						config['green'].blink()
						time.sleep(3)
						config['green'].blink()
					else:
						logger.error('Failed to post data to WUndergroun')
						config['red'].blink()
						time.sleep(3)
						config['red'].blink()
					
				else:
					logger.warning('Most recent archive entry is too old, skipping update')
			else:
				logger.warning('Too few updates to send data to WUnderground')
				
		## Check to see if any of the threads have stopped
		stopped = False
		for t in threads:
			if not t.alive.isSet():
				stopped = True
				break
				
		## If so we are done
		if stopped:
			break
			
		## Done
		t1 = time.time()
		tSleep = config['duration'] - (t1-t0)
		
		## Sleep
		time.sleep(tSleep)
		
	#  Shutdown the remaining threads
	for t in threads:
		t.stop()
		
	# Stop the logger
	logger.info('Finished')	
	logging.shutdown()


if __name__ == "__main__":
	daemonize('/dev/null', '/dev/null', '/tmp/wxPi.stderr')
	main(sys.argv[1:])
	