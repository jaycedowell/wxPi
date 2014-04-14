# -*- coding: utf-8 -*-

"""
Background threads for monitoring the weather and sending the data to 
WUnderground.
"""

import sys
import time
import logging
import threading
import traceback
try:
	import cStringIO as StringIO
except ImportError:
	import StringIO
	
from decoder import read433
from parser import parsePacketStream
from utils import computeDewPoint, computeSeaLevelPressure, generateWeatherReport, wuUploader

from sensors.bmpBackend import BMP085


__version__ = "0.1"
__all__ = ["RadioMonitor", "BMP085Monitor", "__version__", "__all__"]


# Setup the logger
wxThreadsLogger = logging.getLogger('__main__')


class ThreadBase(object):
	"""
	Base class for the various thread defined in this module.
	"""
	
	def __init__(self, config, state, db):
		"""
		Initialize the object with a configuration dictionary, a State 
		instance, and an Archive instance.
		"""
		
		# Basic configuration
		self.config = config
		self.state = state
		self.db = db
		
		# Thread information
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		"""
		Start the background thread.
		"""
		
		if self.thread is not None:
			self.stop()
			       
		self.thread = threading.Thread(target=self.run, name=type(self).__name__)
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
			
	def stop(self):
		"""
		Stop the background thread.
		"""
		
		if self.thread is not None:
			self.alive.clear()
			self.thread.join()
			self.thread = None
			
	def run(self):
		"""
		Function to be run in the background.  This needs to be overridden 
		by the various sub-classes.
		"""
		
		pass


class RadioMonitor(ThreadBase):
	"""
	Thread for monitoring the 433MHz radio and parsing the data as it 
	comes in.
	"""

	def run(self):
		"""
		Monitor the radio looking for data.
		"""
	
		try:	
			read433(self.config['radioPin'], self.callback)
			
		except Exception, e:
			exc_type, exc_value, exc_traceback = sys.exc_info()
			wxThreadsLogger.error("%s: run failed with: %s at line %i", 
									type(self).__name__, str(e), traceback.tb_lineno(exc_traceback))
									
			## Grab the full traceback and save it to a string via StringIO
			fileObject = StringIO.StringIO()
			traceback.print_tb(exc_traceback, file=fileObject)
			tbString = fileObject.getvalue()
			fileObject.close()
			## Print the traceback to the logger as a series of DEBUG messages
			for line in tbString.split('\n'):
					wxThreadsLogger.debug("%s", line)
					
		return True
			
	def callback(self, packets):
		"""
		Callback for updating the current state with the latest data from 
		the radio.
		"""
		
		## Log this packet in debugging mode
		wxThreadsLogger.debug("%s: callback got data '%s'", type(self).__name__, packets)
		
		## Turn on the red LED
		self.config['red'].on()
			
		## Acquire the lock on the current state
		self.state.lock()
		
		## Get the current state
		tData, sensorData = self.state.get()
		
		## Parse the available data
		tData = time.time()
		packets = [tuple(packets.split(None, 1)),]
		sensorData = parsePacketStream(packets, elevation=self.config['elevation'], 
										inputDataDict=sensorData)
		
		## Save the current state
		self.state.set(tData, sensorData)
		
		## Release the lock
		self.state.unlock()
							
		## Turn on the red LED
		self.config['red'].off()
			
		return True


class BMP085Monitor(ThreadBase):
	"""
	Thread for monitoring the pressure and temperature from a BMP085/180
	pressure sensor via I2C.
	"""

	def run(self):
		"""
		Periodically poll the BMP085/180 to get data.
		"""
		
		while self.alive.isSet():
			## Begin the loop
			t0 = time.time()
		
			## Turn on the red LED
			self.config['red'].on()
			
			try:
				## Read the sensor data
				ps = BMP085(address=0x77, mode=3)
				pressure = ps.readPressure() / 100.0 
				temperature = ps.readTemperature()
				
				## Get the lock on the current state
				self.state.lock()
			
				## Get the current state
				tData, sensorData = self.state.get()
			
				## Process the sensor data
				tData = time.time()
				sensorData['pressure'] = pressure
				sensorData['pressure'] = computeSeaLevelPressure(sensorData['pressure'], self.config['elevation'])
				if 'indoorHumidity' in sensorData.keys():
					sensorData['indoorTemperature'] = temperature
					sensorData['indoorDewpoint'] = computeDewPoint(sensorData['indoorTemperature'], sensorData['indoorHumidity'])
						
				## Save the current state
				self.state.set(tData, sensorData)
			
				## Release lock on the current state
				self.state.unlock()
				
			except Exception, e:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				wxThreadsLogger.error("%s: run failed with: %s at line %i", 
										type(self).__name__, str(e), traceback.tb_lineno(exc_traceback))
										
				## Grab the full traceback and save it to a string via StringIO
				fileObject = StringIO.StringIO()
				traceback.print_tb(exc_traceback, file=fileObject)
				tbString = fileObject.getvalue()
				fileObject.close()
				## Print the traceback to the logger as a series of DEBUG messages
				for line in tbString.split('\n'):
					wxThreadsLogger.debug("%s", line)
					
			## Turn off the red LED
			self.config['red'].off()
			
			## Done
			t1 = time.time()
			tSleep = self.config['duration'] - (t1-t0)
			
			## Sleep
			time.sleep(tSleep)