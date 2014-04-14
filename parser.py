# -*- coding: utf-8 -*-

"""
Function for parsing data packets from Oregon Scientific weather sensors
"""

from utils import computeDewPoint, computeWindchill, computeSeaLevelPressure

__version__ = '0.2'
__all__ = ['computeChecksum', 'parsePacketv21', 'parsePacketStream', 
           '__version__', '__all__']


def computeChecksum(bits):
	"""
	Compute the byte-based checksum for a sequence of bits.
	"""
	
	# Bits -> Integers
	values = [int(v, 16) for v in bits]
	
	# Sum
	value = sum(values)
	
	# Convert to an 8-bit value
	value = (value & 0xFF) + (value >> 8)
	
	# Done
	return value


def _parseBHTR968(data):
	"""
	Parse the data section of a BHTR968 indoor temperature/humidity/pressure
	sensor packet and return a dictionary of the values recovered.
	"""
	
	output = {'temperature': -99, 'humidity': -99, 'pressure': -99, 
			  'comfortLevel': 'unknown', 'forecast': 'unknown'}
			  
	# Indoor temperature in C
	temp = data[0:3][::-1]
	temp = int(temp)/10.0
	if int(data[3]) != 0:
		temp *= -1
	output['temperature'] = temp
	
	# Indoor relative humidity as a percentage
	humi = data[4:6][::-1]
	humi = int(humi)
	output['humidity'] = humi
		
	# Indoor "comfort level"
	comf = int(data[6], 16)
	if comf == 0:
		output['comfortLevel'] = 'normal'
	elif comf == 4:
		output['comfortLevel'] = 'comfortable'
	elif comf == 8:
		output['comfortLevel'] = 'dry'
	elif comf == 0xC:
		output['comfortLevel'] = 'wet'
	else:
		output['comfortLevel'] = 'unknown'
		
	# Barometric pressure in mbar
	baro = data[7:9][::-1]
	baro = int(baro, 16)
	if baro >= 128:
		baro -= 256
	output['pressure'] = baro + 856
		
	# Pressure-based weather forecast
	fore = int(data[10], 16)
	if fore == 2:
		output['forecast'] = 'cloudy'
	elif fore == 3:
		output['forecast']  = 'rainy'
	elif fore == 6:
		output['forecast']  = 'partly cloudy'
	elif fore == 0xC:
		output['forecast']  = 'sunny'
	else:
		output['forecast']  = 'unknown'
		
	return output

def _parseRGR968(data):
	"""
	Parse the data section of a RGR968 rain gauge packet and return a dictionary 
	of the values recovered.
	"""
	
	output = {'rainrate': -99, 'rainfall': -99}
	
	# Rainfall rate in mm/hr
	rrate = int(data[0:3][::-1])/10.0
	output['rainrate'] = rrate
	
	# Total rainfall in mm
	rtotl = int(data[3:8][::-1])/10.0
	output['rainfall'] = rtotl
	
	return output

def _parseWGR968(data):
	"""
	Parse the data section of a WGR968 anemometer packet and return a dictionary 
	of the values recovered.
	"""
	
	output = {'average': -99, 'gust': -99, 'direction': -99}
	
	# Wind direction in degrees (N = 0)
	wdir = int(data[0:3][::-1])
	output['direction'] = wdir
	
	# Gust wind speed in m/s
	gspd = int(data[3:6][::-1])/10.0
	output['gust'] = gspd
	
	# Average wind speed in m/s
	aspd = int(data[6:9][::-1])/10.0
	output['average'] = aspd
	
	return output
	
def _parseTHGR268(data):
	"""
	Parse the data section of a THGR268 temperature/humidity sensor packet and return a dictionary 
	of the values recovered.
	"""
	
	output = {'temperature': -99, 'humidity': -99}
	
	# Temperature in C
	temp = int(data[0:3][::-1])/10.0
	if int(data[3]) != 0:
		temp *= -1
	output['temperature'] = temp
		
	# Relative humidity as a percentage
	humi = int(data[4:6][::-1])
	output['humidity'] = humi
	
	return output

def _parseTHGR968(data):
	"""
	Parse the data section of a THGR268 temperature/humidity sensor packet and return a dictionary 
	of the values recovered.
	"""
	
	output = {'temperature': -99, 'humidity': -99}
	
	# Temperature in C
	temp = int(data[0:3][::-1])/10.0
	if int(data[3]) != 0:
		temp *= -1
	output['temperature'] = temp
		
	# Relative humidity as a percentage
	humi = int(data[4:6][::-1])
	output['humidity'] = humi
	
	return output
	
def parsePacketv21(packet, wxData=None, verbose=False):
	"""
	Given a sequence of bits try to find a valid Oregon Scientific v2.1 
	packet.  This function returns a status code of whether or not the packet
	is valid, the sensor name, the channel number, and a dictionary of the 
	values recovered.
	
	Supported Sensors:
	  * 5D60 - BHTR968 - Indoor temperature/humidity/pressure
	  * 2D10 - RGR968  - Rain gauge
	  * 3D00 - WGR968  - Anemometer
	  * 1D20 - THGR268 - Outdoor temperature/humidity
	  * 1D30 - THGR968 - Outdoor temperature/humidity
	"""
	
	# Consolidate
	packet = ''.join(packet)
	
	# Check for a valid sync word.
	if packet[0] != 'A':
		return False, 'Invalid', -1, {}
		
	# Try to figure out which sensor is present so that we can get 
	# the packet length
	sensor = packet[1:5]
	if sensor == '5D60':
		nm = 'BHTR968'
	elif sensor == '2D10':
		nm = 'RGR968'
	elif sensor == '3D00':
		nm = 'WGR968'
	elif sensor == '1D20':
		nm = 'THGR268'
	elif sensor == '1D30':
		nm = 'THGR968'
	else:
		## Unknown - fail
		return False, 'Invalid', -1, {}
			
	## Make sure there are enough bits that we get a checksum
	#if len(packet) < ds+8:
	#	return False, 'Invalid', -1, {}
		
	# Report
	if verbose:
		print 'sync     ', packet[ 0: 1]
		print 'sensor   ', packet[ 1: 5]
		print 'channel  ', packet[ 5: 6]
		print 'code     ', packet[ 6: 8]
		print 'flags    ', packet[ 8: 9]
		print 'data     ', packet[ 9:-4]
		print 'checksum ', packet[-4:-2]
		print 'postamble', packet[-2:]
		print '---------'
		
	# Compute the checksum and compare it to what is in the packet
	ccs = computeChecksum(packet[1:-4])
	ccs = "%02X" % ccs
	if verbose:
		print 'computed ', ccs[::-1]
		print 'valid    ', ccs[::-1] == packet[-4:-2]
		print '---------'
		
	if packet[-4:-2] != ccs[::-1]:
		return False, 'Invalid', -1, {}
		
	# Parse
	data = packet[9:-4]
	channel = int(packet[5])
	if nm == 'BHTR968':
		output = _parseBHTR968(data)
	elif nm == 'RGR968':
		output = _parseRGR968(data)
	elif nm == 'WGR968':
		output = _parseWGR968(data)
	elif nm == 'THGR268':
		output = _parseTHGR268(data)
	elif nm == 'THGR968':
		output = _parseTHGR968(data)
	else:
		return False, 'Invalid', -1, {}
		
	# Report
	if verbose:
		print output
		
	# Return the packet validity, channel, and data dictionary
	return True, nm, channel, output


def parsePacketStream(packets, elevation=0.0, inputDataDict=None, verbose=False):
	"""
	Given a sequence of two-element type,payload packets from read433, 
	find all of the Oregon Scientific sensor values and return the data 
	as a dictionary.  In the process, compute various derived quantities 
	(dew point, windchill, and sea level correctedpressure).
	
	.. note::
		The sea level corrected pressure is only compute if the elevation 
		(in meters) is set to a non-zero value.  
	"""

	# Setup the output dictionary
	output = {}
	if inputDataDict is not None:
		for key,value in inputDataDict.iteritems():
			output[key] = value

	# Parse the packet payload and save the output
	for pType,pPayload in packets:
		if pType == 'OSV2':
			valid, sensorName, channel, sensorData = parsePacketv21(pPayload, verbose=verbose)
		else:
			continue
			
		## Data reorganization and computed quantities
		if valid:
			### Dew point - indoor and output
			if sensorName in ('BHTR968', 'THGR268', 'THGR968'):
				sensorData['dewpoint'] = computeDewPoint(sensorData['temperature'], sensorData['humidity'])
			### Sea level corrected barometric pressure
			if sensorName in ('BHTR968',) and elevation != 0.0:
				sensorData['pressure'] = computeSeaLevelPressure(sensorData['pressure'], elevation)
			### Disentangle the indoor temperatures from the outdoor temperatures
			if sensorName == 'BHTR968':
				for key in ('temperature', 'humidity', 'dewpoint'):
					newKey = 'indoor%s' % key.capitalize()
					sensorData[newKey] = sensorData[key]
					del sensorData[key]
			### Multiplex the THGR268 values
			for key in sensorData.keys():
				if key in ('temperature', 'humidity', 'dewpoint'):
					if sensorName == 'THGR968':
						output[key] = sensorData[key]
					else:
						try:
							output['alt%s' % key.capitalize()][channel-1] = sensorData[key]
						except KeyError:
							output['alt%s' % key.capitalize()] = [None, None, None, None]
							output['alt%s' % key.capitalize()][channel-1] = sensorData[key]
				else:
					output[key] = sensorData[key]
					
	# Compute combined quantities
	if 'temperature' in output.keys() and 'average' in output.keys():
		output['windchill'] = computeWindchill(output['temperature'], output['average'])

	# Done
	return output


if __name__ == "__main__":
	# Testing
	packets = [('OSV2', 'A1D201BB05710818544A'), 
	           ('OSV2', 'A1D3012200710618D2E0'), 
	           ('OSV2', 'A3D000470712930730B3AE'), 
	           ('OSV2', 'A5D600BB09220528CD83E6AF'),]
	output = parsePacketStream(packets, verbose=True)
