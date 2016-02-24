"""
Module for interfacing with the sqlite3 database.
"""

import os
import sys
import time
import uuid
import Queue
import logging
import sqlite3
import threading
import traceback
from ConfigParser import NoSectionError
from datetime import datetime
try:
	import cStringIO as StringIO
except ImportError:
	import StringIO

__version__ = "0.2"
__all__ = ["Archive", "__version__", "__all__"]


# Logger instance
dbLogger = logging.getLogger('__main__')


class DatabaseProcessor(threading.Thread):
	"""
	Class responsible for providing access to the database from a single thread.
	"""
	
	def __init__(self, dbName):
		self._dbName = dbName
		self.running = False
		self.input = Queue.Queue()
		self.output = Queue.Queue()
		
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		if self.thread is not None:
			self.cancel()
        	       
		self.thread = threading.Thread(target=self.run, name='dbAccess')
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
		
		dbLogger.info('Started the DatabaseProcessor background thread')
		
	def cancel(self):
		if self.thread is not None:
			self.alive.clear()          # clear alive event for thread
			self.thread.join()
			
		dbLogger.info('Stopped the DatabaseProcessor background thread')
			
	def appendRequest(self, cmd):
		rid = str(uuid.uuid4())
		self.input.put( (rid,cmd) )
		
		return rid
		
	def getResponse(self, rid):
		qid, qresp = self.output.get()
		while qid != rid:
			self.output.put( (qid,qresp) )
			qid, qresp = self.output.get()
			
		return qresp
		
	def dict_factory(self, cursor, row):
		d = {}
		for idx, col in enumerate(cursor.description):
			d[col[0]] = row[idx]
		return d
		
	def run(self):
		self._dbConn = sqlite3.connect(self._dbName)
		self._dbConn.row_factory = self.dict_factory
		self._cursor = self._dbConn.cursor()
		
		while self.alive.isSet() or not self.input.empty():
			try:
				rid, cmd = self.input.get()
				self._cursor.execute(cmd)
				output = []
				for row in self._cursor.fetchall():
					output.append( row )
				if cmd[:6] != 'SELECT':
					self._dbConn.commit()
				self.output.put( (rid,output) )
				
			except Exception, e:
				exc_type, exc_value, exc_traceback = sys.exc_info()
				dbLogger.error("DatabaseProcessor: %s at line %i", e, traceback.tb_lineno(exc_traceback))
				## Grab the full traceback and save it to a string via StringIO
                fileObject = StringIO.StringIO()
                traceback.print_tb(exc_traceback, file=fileObject)
                tbString = fileObject.getvalue()
                fileObject.close()
                ## Print the traceback to the logger as a series of DEBUG messages
                for line in tbString.split('\n'):
                	dbLogger.debug("%s", line)
					
		self._dbConn.close()


class Archive(object):
	_dbConn = None
	_cursor = None
	
	_dbMapper = {'temperature': 'outTemp', 
				 'humidity': 'outHumidity', 
				 'dewpoint': 'outDewpoint', 
				 'windchill': 'windchill', 
				 'indoorTemperature': 'inTemp', 
				 'indoorHumidity': 'inHumidity',
				 'indoorDewpoint': 'inDewpoint', 
				 'pressure': 'barometer',
				 'average': 'windSpeed', 
				 'gust': 'windGust', 
				 'direction': 'windDir',
				 'rainrate': 'rainRate', 
				 'rainfall': 'rain',
				 'uvIndex': 'uv'}
				 
	def __init__(self):
		self._dbName = os.path.join(os.path.dirname(__file__), 'archive', 'wx-data.db')
		if not os.path.exists(self._dbName):
			raise RuntimeError("Archive database not found")
		self._backend = None
		
	def start(self):
		"""
		Open the database.
		"""
		
		if self._backend is None:
			self._backend = DatabaseProcessor(self._dbName)
		self._backend.start()
		
	def cancel(self):
		"""
		Close the database.
		"""
	
		if self._backend is not None:
			self._backend.cancel()
			
	def getData(self, age=0):
		"""
		Return a collection of data a certain number of seconds into the past.
		"""
		
		# Fetch the entries that match
		if age <= 0:
			sqlCmd = 'SELECT * FROM wx ORDER BY dateTime DESC LIMIT 1'
			rid = self._backend.appendRequest(sqlCmd)
		else:
			# Figure out how far to look back into the database
			tNow = time.time()
			tLookback = tNow - age
			sqlCmd = 'SELECT * FROM wx WHERE dateTime >= %i ORDER BY dateTime LIMIT 1' % tLookback
			rid = self._backend.appendRequest(sqlCmd)
			
		# Fetch the output
		output = self._backend.getResponse(rid)
		row = output[0]

		# Check for an empty database
		if row is None:
			return 0, {}
			
		# Convert it to the "standard" dictionary format
		timestamp = row['dateTime']
		output = {'temperature': row['outTemp'], 'humidity': row['outHumidity'], 
		          'dewpoint': row['outDewpoint'], 'windchill': row['windchill'], 
		          'indoorTemperature': row['inTemp'], 'indoorHumidity': row['inHumidity'], 
		          'indoorDewpoint': row['inDewpoint'], 'pressure': row['barometer'], 
		          'rainrate': row['rainRate'], 'rainfall': row['rain'], 
		          'average': row['windSpeed'], 'gust': row['windGust'], 'direction': row['windDir'], 
			  'altTemperature': [], 'altHumidity': [], 'altDewpoint': [],
			  'uvIndex': row['uv']}
		for i in xrange(1, 5):
			output['altTemperature'].append( row['outTemp%i' % i] if row['outTemp%i' % i] != -99 else None )
			output['altHumidity'].append( row['outHumidity%i' % i] if row['outHumidity%i' % i] != -99 else None )
			output['altDewpoint'].append( row['outDewpoint%i' % i] if row['outDewpoint%i' % i] != -99 else None )
			
		# Get the rainfall relative to the start of the year
		
		return timestamp, output
		
	def getDataYearStart(self):
		tNow = datetime.now()
		tYear = tNow.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
		tYear = int( tYear.strftime("%s") )
		
		sqlCmd = 'SELECT * FROM wx WHERE dateTime >= %i ORDER BY dateTime LIMIT 1' % tYear
		rid = self._backend.appendRequest(sqlCmd)
			
		# Fetch the output
		output = self._backend.getResponse(rid)
		row = output[0]
		
		# Check for an empty database
		if row is None:
			return 0, {}
			
		# Convert it to the "standard" dictionary format
		timestamp = row['dateTime']
		output = {'temperature': row['outTemp'], 'humidity': row['outHumidity'], 
		          'dewpoint': row['outDewpoint'], 'windchill': row['windchill'], 
		          'indoorTemperature': row['inTemp'], 'indoorHumidity': row['inHumidity'], 
		          'indoorDewpoint': row['inDewpoint'], 'pressure': row['barometer'], 
		          'rainrate': row['rainRate'], 'rainfall': row['rain'], 
		          'average': row['windSpeed'], 'gust': row['windGust'], 'direction': row['windDir'], 
			  'altTemperature': [], 'altHumidity': [], 'altDewpoint': [],
			  'uvIndex': row['uv']}
		for i in xrange(1, 5):
			output['altTemperature'].append( row['outTemp%i' % i] if row['outTemp%i' % i] != -99 else None )
			output['altHumidity'].append( row['outHumidity%i' % i] if row['outHumidity%i' % i] != -99 else None )
			output['altDewpoint'].append( row['outDewpoint%i' % i] if row['outDewpoint%i' % i] != -99 else None )
			
		return timestamp, output

	def writeData(self, timestamp, data):
		"""
		Write a collection of data to the database.
		"""
		
		# Build up the values to insert
		cNames = ['dateTime', 'usUnits']
		dValues = [int(timestamp), 0]
		for key in data.keys():
			try:
				cNames.append( self._dbMapper[key] )
				dValues.append( data[key] )
			except KeyError:
				if key[:3] == 'alt':
					if key[3:6] == 'Tem':
						nameBase = 'outTemp'
					elif key[3:6] == 'Hum':
						nameBase = 'outHumidity'
					else:
						nameBase = 'outDewpoint'
						
					for i in xrange(len(data[key])):
						if data[key][i] is not None:
							cNames.append( "%s%i" % (nameBase, i+1) )
							dValues.append( data[key][i] )
							
		# Add the entry to the database
		rid = self._backend.appendRequest('INSERT INTO wx (%s) VALUES (%s)' % (','.join(cNames), ','.join([str(v) for v in dValues])))
		output = self._backend.getResponse(rid)
		
		return True
