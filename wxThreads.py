import time
import logging
import threading

from database import Archive
from decoder import read433
from parser import parsePacketStream
from utils import computeDewPoint, computeSeaLevelPressure, generateWeatherReport, wuUploader

from led import LED
from sensors.bmpBackend import BMP085


__version__ = "0.1"
__revision__ = "$Rev$"
__all__ = ["initState", "RadioMonitor", "BMP085Monitor", "Archiver", "Uploader", "__version__", "__revision__", "__all__"]


# The current weather data state and its lock
class State(object):
	def __init__(self):
		self.tData = 0.0
		self.sensorData = {}
		self._lock = threading.Semaphore()
		
	def lock(self):
		self._lock.acquire()
		
	def unlock(self):
		self._lock.release()
		
	def set(self, tData, sensorData):
		self.tData = tData
		self.sensorData = sensorData
		
	def get(self):
		return self.tData, self.sensorData


def initState(config):
	"""
	Initialize the current state using values stored in the database.
	"""
	
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
		
	# Create the state
	state = State()
	state.set(tData, sensorData)
	
	# Return the database instance
	return db, state


class RadioMonitor(object):
	def __init__(self, config, state, db):
		# Basic configuration
		self.config = config
		self.state = state
		self.db = db
		
		# Thread information
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		"""
		Start the radio monitor.
		"""
		
		if self.thread is not None:
			self.stop()
			       
		self.thread = threading.Thread(target=self.run, name='radio')
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
			
	def stop(self):
		"""
		Stop the radio monitor.
		"""
		
		if self.thread is not None:
			self.alive.clear()
			self.thread.join()
			self.thread = None
			
	def run(self):
		"""
		Monitor the radio looking for data
		"""
	
		try:	
			read433(self.config['radioPin'], self.callback)
		except Exception, e:
			logging.error(str(e))
			
		return True
			
	def callback(self, packets):
		"""
		Callback for updating the current state with the latest data
		"""
		
		## Log this packet in debugging mode
		logging.debug("Got packets: %s" % str(packets))
		
		## Acquire the lock on the current state
		self.state.lock()
	
		## Turn on the red LED
                self.config['red'].on()
			
		## Get the current state
		tData, sensorData = self.state.get()
		
		## Parse the available data
		tData = time.time()
		packets = [tuple(packets.split(None, 1)),]
		sensorData = parsePacketStream(packets, elevation=self.config['elevation'], inputDataDict=sensorData, verbose=self.config['verbose'])
		
		## Save the current state
		self.state.set(tData, sensorData)
								
		## Turn on the red LED
		self.config['red'].off()
			
		## Release the lock
		self.state.unlock()
		
		return True


class BMP085Monitor(object):
	def __init__(self, config, state, db):
		# Basic configuration
		self.config = config
		self.state = state
		self.db = db
		
		# Thread information
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		"""
		Start the BMP085/180 monitor.
		"""
		
		if self.thread is not None:
			self.stop()
			       
		self.thread = threading.Thread(target=self.run, name='bmp')
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
		
	def stop(self):
		"""
		Stop the BMP085/180 monitor.
		"""
		
		if self.thread is not None:
			self.alive.clear()
			self.thread.join()
			self.thread = None
			
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
			p = ps.readPressure() / 100.0 
			t = ps.readTemperature()
			
			tData = time.time()
			sensorData['pressure'] = p
			sensorData['pressure'] = computeSeaLevelPressure(sensorData['pressure'], self.config['elevation'])
			if 'indoorHumidity' in sensorData.keys():
				sensorData['indoorTemperature'] = t
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


class Archiver(object):
	def __init__(self, config, state, db):
		# Basic configuration
		self.config = config
		self.state = state
		self.db = db
		
		# Thread information
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		"""
		Start the data archiver.
		"""
		
		if self.thread is not None:
			self.stop()
			       
		self.thread = threading.Thread(target=self.run, name='arc')
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
		
	def stop(self):
		"""
		Stop the data archiver.
		"""
		
		if self.thread is not None:
			self.alive.clear()
			self.thread.join()
			self.thread = None
			
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
					
					logging.info('Saving current state to archive')
					
			## Turn off the yellow LED
			self.config['yellow'].off()
			
			## Release lock on the current state
			self.state.unlock()
			
			## Done
			t1 = time.time()
			tSleep = self.config['duration'] - (t1-t0)
			
			## Sleep
			time.sleep(tSleep)


class Uploader(object):
	def __init__(self, config, state, db):
		# Basic configuration
		self.config = config
		self.state = state
		self.db = db
		
		# Thread information
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		"""
		Start the WUnderground uploader.
		"""
		
		if self.thread is not None:
			self.stop()
			       
		self.thread = threading.Thread(target=self.run, name='wuu')
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
		
	def stop(self):
		"""
		Stop the WUnderground uploader.
		"""
		
		if self.thread is not None:
			self.alive.clear()
			self.thread.join()
			self.thread = None
			
	def run(self):
		"""
		Post the latest weather data to WUnderground.
		"""
		
		# State variable to keep up with what has and hasn't been sent
		tLastUpdate = 0.0
		
		while self.alive.isSet():
			## Get the latest batch of data
			t, d = db.getData()
		
			# Make sure that it is fresh so that we only send the latest and greatest
			if t != tLastUpdate:
				#uploadStatus = wuUploader(self.config['ID'], self.config['PASSWORD'], 
				#					t, d, archive=self.db, 
				#					includeIndoor=self.config['includeIndoor'], 
				#					verbose=self.config['verbose'])
				#					
				#if uploadStatus:
				#	tLastUpdate = 1.0*tData
				
				logger.info('Posted data to WUnderground')
				self.config['green'].blink()
				time.sleep(3)
				self.config['green'].blink()
				
			## Done
			t1 = time.time()
			tSleep = self.config['duration'] - (t1-t0)
		
			if not self.alive.isSet():
				break
				
			## Sleep
			time.sleep(tSleep)
