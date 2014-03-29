#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script to record 433MHz dat in search of packets from Oregon Scientific 
weather sensors and a BMP085/180, and send the results to WUnderground.

This script takes no arguments.
"""

import sys
import time

from config import CONFIG_FILE, loadConfig
from database import Archive
from decoder import read433
from parser import parsePacketStream
from utils import computeDewPoint, computeSeaLevelPressure, generateWeatherReport, wuUploader

from led import on as ledOn, off as ledOff, blinkOn, blinkOff
from sensors.bmpBackend import BMP085

def main(args):
	# Read in the configuration file
	config = loadConfig(CONFIG_FILE)
	
	# Record some data and extract the bits on-the-fly
	ledOn(config['redPin'])
	packets = read433(config['radioPin'], int(round(config['duration'])), 
				verbose=config['verbose'])
	ledOff(config['redPin'])
	
	# Read in the most recent state
	ledOn(config['yellowPin'])
	try:
		db = Archive()
		tLast, output = db.getData()
	except RuntimeError, e:
		print "WARNING: %s" % str(e)
		
		db = None
		tLast, output = time.time(), {}
		
	# Find the packets and save the output
	output = parsePacketStream(packets, elevation=config['elevation'], inputDataDict=output, verbose=config['verbose'])
	ledOff(config['yellowPin'])	

	# Poll the BMP085/180
	if config['enableBMP085']:
		ledOn(config['redPin'])
		ps = BMP085(address=0x77, mode=3)
		output['pressure'] = ps.readPressure() / 100.0 
		output['pressure'] = computeSeaLevelPressure(output['pressure'], config['elevation'])
		if 'indoorHumidity' in output.keys():
			output['indoorTemperature'] = ps.readTemperature()
			output['indoorDewpoint'] = computeDewPoint(output['indoorTemperature'], output['indoorHumidity'])
		ledOff(config['redPin'])
	
	# Save to the database
	ledOn(config['yellowPin'])
	if db is not None:
		db.writeData(time.time(), output)
		
	# Upload
	status = wuUploader(config['ID'], config['PASSWORD'], output, archive=db, 
				includeIndoor=config['includeIndoor'], verbose=config['verbose'])
	ledOff(config['yellowPin'])
	
	# Report status of upload...
	if status:
		ledColor = config['greenPin']
	else:
		ledColor = config['redPin']
	# ... with an LED
	blinkOn(ledColor)
	time.sleep(3)
	blinkOff(ledColor)
	ledOff(ledColor)


if __name__ == "__main__":
	main(sys.argv[1:])
