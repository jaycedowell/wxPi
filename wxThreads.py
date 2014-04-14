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

from led import LED
from sensors.bmpBackend import BMP085


__version__ = "0.1"
__all__ = ["RadioMonitor", "BMP085Monitor", "Archiver", "Uploader", "__version__", "__all__"]


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
		
		## Acquire the lock on the current state
		self.state.lock()
		
		## Turn on the red LED
		self.config['red'].on()
			
		## Get the current state
		tData, sensorData = self.state.get()
		
		## Parse the available data
		tData = time.time()
		packets = [tuple(packets.split(None, 1)),]
		sensorData = parsePacketStream(packets, elevation=self.config['elevation'], 
										inputDataDict=sensorData)
		
		## Save the current state
		self.state.set(tData, sensorData)
								
		## Turn on the red LED
		self.config['red'].off()
			
		## Release the lock
		self.state.unlock()
		
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
			
			## Get the lock on the current state
			self.state.lock()
			
			## Turn on the red LED
			self.config['red'].on()
			
			## Get the current state
			tData, sensorData = self.state.get()
			
			## Read the sensor data
			ps = BMP085(address=0x77, mode=3)
			pressure = ps.readPressure() / 100.0 
			temperature = ps.readTemperature()
			
			tData = time.time()
			sensorData['pressure'] = pressure
			sensorData['pressure'] = computeSeaLevelPressure(sensorData['pressure'], self.config['elevation'])
			if 'indoorHumidity' in sensorData.keys():
				sensorData['indoorTemperature'] = temperature
				sensorData['indoorDewpoint'] = computeDewPoint(sensorData['indoorTemperature'], sensorData['indoorHumidity'])
				
			## Save the current state
			self.state.set(tData, sensorData)
			
			## Turn off the red LED
			self.config['red'].off()
			
			## Release lock on the current state
			self.state.release()
			
			## Done
			t1 = time.time()
			tSleep = self.config['duration'] - (t1-t0)
			
			## Sleep
			time.sleep(tSleep)


class Archiver(ThreadBase):
	"""
	Thread to write the current state to the archive at regular intervals.
	"""
	
	def run(self):
		"""
		Archive the current data to the archive.
		"""
		
		# State variable to keep up with what has and hasn't been sent
		tLastUpdate = 0.0
		
		while self.alive.isSet():
			## Begin the loop
			t0 = time.time()
			
			## Get the lock on the current state
			self.state.lock()
			
			## Turn on the yellow LED
			self.config['yellow'].on()
			
			## Get the current state
			tData, sensorData = self.state.get()
			
			## Check if there is anything to update
			if tData != tLastUpdate:
				if len(sensorData.keys()) > 0:
					db.writeData(tData, sensorData)
					tLastUpdate = 1.0*tData
					
					wxThreadsLogger.info('%s: Saving current state to archive', type(self).__name__)
					
			## Turn off the yellow LED
			self.config['yellow'].off()
			
			## Release lock on the current state
			self.state.unlock()
			
			## Done
			t1 = time.time()
			tSleep = self.config['duration'] - (t1-t0)
			
			## Sleep
			time.sleep(tSleep)


class Uploader(ThreadBase):
	"""
	Thread for sending periodic updates to the WUnderground PWS service.
	"""
	
	def run(self):
		"""
		Post the latest weather data to WUnderground.
		"""
		
		# State variable to keep up with what has and hasn't been sent
		tLastUpdate = 0.0
		
		while self.alive.isSet():
			## Get the latest batch of data
			tData, sensorData = self.db.getData()
		
			# Make sure that it is fresh so that we only send the latest and greatest
			if tData != tLastUpdate:
				if time.time()-tData < 2*self.config['duration']:
					uploadStatus = wuUploader(self.config['ID'], self.config['PASSWORD'], 
										tData, sensorData, archive=self.db, 
										includeIndoor=self.config['includeIndoor'])
										
					if uploadStatus:
						tLastUpdate = 1.0*tData
						
						wxThreadsLogger.info('Posted data to WUnderground')
						self.config['green'].blink()
						time.sleep(3)
						self.config['green'].blink()
					else:
						wxThreadsLogger.error('Failed to post data to WUndergroun')
						self.config['red'].blink()
						time.sleep(3)
						self.config['red'].blink()
						
				else:
					wxThreadsLogger.warning('Most recent archive entry is too old, skipping update')
					
			## Done
			if not self.alive.isSet():
				break
				
			t1 = time.time()
			tSleep = self.config['duration'] - (t1-t0)
				
			## Sleep
			time.sleep(tSleep)