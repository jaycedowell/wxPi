# -*- coding: utf-8 -*-

"""
Various utility functions needed by wxPi.py
"""

import math
import time
import urllib
import logging
from datetime import datetime

from database import Archive

__version__ = "0.2"
__all__ = ["length_m2ft", "length_ft2m", "length_mm2in", "length_in2mm", 
		   "speed_ms2mph", "speed_mph2ms", 
		   "temp_C2F", "temp_F2C", 
		   "pressure_mb2inHg", "pressure_inHg2mb", 
		   "computeDewPoint", "computeWindchill", "computeSeaLevelPressure", 
		   "generateWeatherReport", "wuUploader", "__version__", "__all__"]


# Setup the logger
utilsLogger = logging.getLogger('__main__')


def length_m2ft(value):
	"""
	Convert a length in meters to feet.
	"""
	
	return value*3.28084
	
def length_ft2m(value):
	"""
	Convert a length in feet to meters.
	"""
	
	return value/3.28084
	
def length_mm2in(value):
	"""
	Convert a length in millimeters to inches.
	"""
	
	return value/25.4
	
def length_in2mm(value):
	"""
	Convert a length in inches to millimeters.
	"""
	
	return value*25.4


def speed_ms2mph(value):
	"""
	Convert a speed in m/s to mph.
	"""
	
	return value*2.23694
	
def speed_mph2ms(value):
	"""
	Convert a speed in mph to m/s.
	"""
	
	return value/2.23694


def temp_C2F(value):
	"""
	Convert a temperature in degrees Celsius to Fahrenheit
	"""

	return value*9.0/5.0 + 32
	
def temp_F2C(value):
	"""
	Convert a temperature in degrees Fahrenheit to Celsius.
	"""
	
	return (value-32.0)*5.0/9.0


def pressure_mb2inHg(value):
	"""
	Convert a barometric pressure in millibar to inches of mercury.
	"""
	
	return value/33.8638866667
	
def pressure_inHg2mb(value):
	"""
	Convert a barometric pressure in inches of mercury to millibar.
	"""
	
	return value*33.8638866667


def computeDewPoint(temp, humidity, degF=False):
	"""
	Given a temperature and a relative humidity, calculate the dew point
	following http://en.wikipedia.org/wiki/Dew_point
	
	Note::
		Temperatures can be be supplied either as Celsius (default) or 
		Fahrenheit.  If a value in Fahrenheit is supplied, you will need 
		to set the 'degF' keyword to True.
		
		The returned dew point is in the same units as the input temperature.
	"""

	# Move to Celsius, if needed
	if degF:
		temp = temp_F2C(temp)
		
	# Compute dew point from http://en.wikipedia.org/wiki/Dew_point
	a = 6.112	# millibar
	b = 17.67	# unitless
	c = 243.5	# degrees C
	Pa = a*math.exp(math.log(humidity/100.0) + b*temp/(c + temp))
	dewpt = c*math.log(Pa/a)/(b - math.log(Pa/a))
	
	# More back to Fahrenheit, if needed
	if degF:
		dewpt = temp_C2F(dewpt)
		
	return dewpt


def computeWindchill(temp, wind, degF=False, mph=False):
	"""
	Compute the windchill using the NWS formula from:
	  http://www.nws.noaa.gov/os/windchill/index.shtml
	  
	Note::
		The temperature can be supplied as either Celsius (default) or 
		Fahrenheit.  If a value in Fahrenheit is supplied, you will need 
		to set the 'degF' keyword to True.
		
		The wind speed can be supplied as either m/s (default) or mph.  If
		a value in mph is supplied, you will need to set the 'mph' keyword
		to True.
		
		The returned windchill is in the same units as the input temperature.
	"""
	
	# Convert to Fahrenheit, if needed
	if not degF:
		temp = temp_C2F(temp)
		
	# Convert to mph, if needed
	if not mph:
		wind = speed_ms2mph(wind)
		
	# Check the limits on the temperature and windspeed
	if temp >= -50.0 and temp <= 50.0 and wind >= 3.0 and wind < 110.0:
		temp = 35.74 + 0.6215*temp - 35.75*wind**0.16 + 0.4275*temp*wind**0.16
		
	# Convert to Celsius, if needed
	if not degF:
		temp = temp_F2C(temp)
		
	return temp


def computeSeaLevelPressure(press, elevation, inHg=False, ft=False):
	"""
	Correct a barometric pressure for elevation using the Barometric 
	formula and the International Standard Atmosphere.
	
	Note::
		The barometric pressure can be supplied in either units of millibar
		(default) or inches of mercury.  If a value in inches of mercury 
		is specified, you will need to set the 'inHg' keyword to True.
		
		The elevation can be supplied in either units of meters (default) or
		feet.  If a value in feet is specified, you will need to set the 'ft'
		keyword to True.
		
		The returned barometric pressure is in the same units as the input
		barometric pressure.
	"""
	
	# Convert to inches of mercury, if needed
	if not inHg:
		press = pressure_mb2inHg(press)
		
	# Convert meters to feet, if needed
	if not ft:
		elevation = length_m2ft(elevation)
		
	# Compute the sea level reference pressure from the Barometric formula
	# and zone 0 (<~36,000 feet)
	# See: http://en.wikipedia.org/wiki/Barometric_formula
	Pb = 29.92126		# in Hg
	Tb = 288.15			# K
	Lb = -0.0019812		# K/ft
	g0 = 32.17405		# ft/s/s
	M  = 28.9644 		# lb/lbmol
	Rs = 8.9494596e4	# lb ft^2/lbmol/K/s/s	
	
	press *= (Tb / (Tb+Lb*elevation))**(-g0*M/(Rs*Lb))
	
	# Convert back to inches of mercury, if needed
	if not inHg:
		press = pressure_inHg2mb(press)
		
	return press


def generateWeatherReport(output, includeIndoor=True):
	"""
	Given a data dictionary created by parseBitStream, generate a string 
	that contains the current weather conditions.
	"""
	
	wxReport = ""
	
	# Indoor
	if includeIndoor and 'indoorTemperature' in output.keys():
		wxReport += "Indoor Conditions:\n"
		wxReport += " -> %.1f F with %i%% humidity\n" % (temp_C2F(output['indoorTemperature']), output['indoorHumidity'])
		wxReport += " -> dew point is %.1f F\n" % (temp_C2F(output['indoorDewpoint']),)
		wxReport += " -> barometric pressure is %.2f in-Hg\n" % pressure_mb2inHg(output['pressure'])
		if 'comfortLevel' in output.keys():
			if output['comfortLevel'] != 'unknown':
				wxReport += " -> comfort level is %s\n" % output['comfortLevel']
		wxReport += "\n"
	
	if 'temperature' in output.keys():
		wxReport += "Outdoor Conditions:\n"
		wxReport += " -> %.1f F with %i%% humidity\n" % (temp_C2F(output['temperature']), output['humidity'])
		wxReport += " -> dew point is %.1f F\n" % (temp_C2F(output['dewpoint']),)
		## Windchill?
		if 'windchill' in output.keys():
			if output['windchill'] != output['temperature']:
				wxReport += " -> windchill is %.1f F\n" % (temp_C2F(output['windchill']),)
		## Alternate temperature/humidity/dew point values?
		if 'altTemperature' in output.keys():
			for i in xrange(4):
				if output['altTemperature'][i] is not None:
					t, h, d = output['altTemperature'][i], output['altHumidity'][i], output['altDewpoint'][i]
					wxReport += "    #%i: %.1f F with %i%% humidity\n" % (i+1, temp_C2F(t), h)
					wxReport += "         dew point is %.1f F\n" % (temp_C2F(d),)
		wxReport += "\n"
		
	if 'average' in output.keys():
		wxReport += "Wind:\n"
		wxReport += "-> average %.1f mph @ %i degrees\n" % (speed_ms2mph(output['average']), output['direction'])
		wxReport += "-> gust %.1f mph\n" % speed_ms2mph(output['gust'])
		wxReport += "\n"
		
	if 'rainrate' in output.keys():
		wxReport += "Rainfall:\n"
		wxReport += " -> %.2f in/hr, %.2f in total\n" % (length_mm2in(output['rainrate']), length_mm2in(output['rainfall']))
		wxReport += "\n"
		
	if 'forecast' in output.keys():
		if output['forecast'] != 'unknown':
			wxReport += "Forecast:\n"
			wxReport += " -> %s\n" % output['forecast']
			wxReport += "\n"
		
	# Done
	return wxReport


def wuUploader(id, password, tData, sensorData, archive=None, includeIndoor=False):
	"""
	Upload a collection of data to the WUnderground PWD service.
	"""
	
	# Wunderground PWS Base URL
	PWS_BASE_URL = "http://weatherstation.wunderground.com/weatherstation/updateweatherstation.php"
	
	# Data dictionary to upload
	pwsData = {}
	
	# Prepare the data for posting
	## Account information, software type, and action
	pwsData['ID'] = id
	pwsData['PASSWORD'] = password
	pwsData['softwaretype'] = "wxPi"
	pwsData['dateutc'] = datetime.utcfromtimestamp(tData).strftime("%Y-%m-%d %H:%M:%S")
	pwsData['action'] = "updateraw"
	
	## Add in the outdoor temperature/humidity values
	try:
		pwsData['tempf'] = round(temp_C2F( sensorData['temperature'] ), 1)
		pwsData['humidity'] = sensorData['humidity']
		pwsData['dewptf'] = round(temp_C2F( sensorData['dewpoint'] ), 1)
	except KeyError:
		pass
	j = 2
	for i in xrange(4):
		try:
			t = sensorData['altTemperature'][i]
			if t is None:
				continue
			pwsData['temp%if' % j] = round(temp_C2F( t ), 1)
		except KeyError:
			pass
			
	## Add in the barometric pressure
	pwsData['baromin'] = round(pressure_mb2inHg( sensorData['pressure'] ), 2)
	
	## Add in the wind values
	try:
		pwsData['windspeedmph'] = round(speed_ms2mph( sensorData['average'] ), 1)
		pwsData['windgustmph'] = round(speed_ms2mph( sensorData['gust'] ), 1)
		pwsData['winddir'] = sensorData['direction']
		pwsData['windgustdir'] = sensorData['gustDirection']
	except KeyError:
		pass
		
	## Add in the UV index
	try:
		if sensorData['uvIndex'] >= 0:
			pwsData['UV'] = sensorData['uvIndex']
	except KeyError:
		pass
		
	## Add in the rain values
	if archive is not None:
		### Ouch... there has to be a better way to do this
		tUTCMidnight = (int(time.time()) / 86400) * 86400
		localOffset = int(round(float(datetime.utcnow().strftime("%s.%f")) - time.time(), 1))
		tLocalMidnight = tUTCMidnight + localOffset
		if tLocalMidnight > time.time():
			tLocalMidnight -= 86400
			
		### Get the rainfall from an hour ago and from local midnight
		ts, entry = archive.getData(age=3630)
		rainHour = entry['rainfall']
		ts, entry  = archive.getData(age=time.time()-tLocalMidnight+30)
		rainDay = entry['rainfall']
		
		### Calculate
		if rainHour >= 0 and rainDay >= 0:
			try:
				rainHour = sensorData['rainfall'] - rainHour
				if rainHour < 0:
					rainHour = 0.0
				rainDay = sensorData['rainfall'] - rainDay
				if rainDay < 0:
					rainDay = 0.0
				pwsData['rainin'] = round(length_mm2in( rainHour ), 2)
				pwsData['dailyrainin'] = round(length_mm2in( rainDay ), 2)
			except KeyError:
				pass
				
	## Add in the indoor values if requested
	if includeIndoor:
		try:
			pwsData['indoortempf'] =  round(temp_C2F( sensorData['indoorTemperature'] ), 1)
			pwsData['indoorhumidity'] = sensorData['indoorHumidity']
		except KeyError:
			pass
			
	# Post to Wunderground for the PWS protocol (if there is something 
	# interesting to send)
	status = False
	if len(pwsData.keys()) > 4:
		## Convert to a GET-safe string
		pwsData = urllib.urlencode(pwsData)
		url = "%s?%s" % (PWS_BASE_URL, pwsData)
		utilsLogger.info('WUnderground upload URL: %s', url)
			
		## Send
		try:
			uh = urllib.urlopen(url)
			status = uh.read()
			utilsLogger.debug('WUnderground PWS update status: %s', status)
		except Exception, e:
			utilsLogger.warning('WUnderground PWS update failed: %s', str(e))
			status = 'failed'
			
		try:
			uh.close()
		except:
			pass
			
		## Evaluate
		if status.find('success') != -1:
			status = True
		else:
			status = False
		
	return status
