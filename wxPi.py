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
from decoder import readRTL
from parser import parseBitStream
from utils import computeDewPoint, computeSeaLevelPressure, generateWeatherReport, wuUploader

from sensors.bmpBackend import BMP085

def main(args):
	# Read in the configuration file
	config = loadConfig(CONFIG_FILE)
	
	# Record some data and extract the bits on-the-fly
	bits = readRTL(int(config['duration']))
	
	# Read in the most recent state
	db = Archive()
	tLast, output = db.getData()
	
	# Find the packets and save the output
	output = parseBitStream(bits, elevation=config['elevation'], inputDataDict=output, verbose=config['verbose'])
	
	# Poll the BMP085/180
	ps = BMP085(address=0x77, mode=3)
	output['pressure'] = ps.readPressure() / 100.0 
	output['pressure'] = computeSeaLevelPressure(output['pressure'], config['elevation'])
	if 'indoorHumidity' in output.keys():
		output['indoorTemperature'] = ps.readTemperature()
		output['indoorDewpoint'] = computeDewPoint(output['indoorTemperature'], output['indoorHumidity'])
		
	# Save to the database
	db.writeData(time.time(), output)
	
	# Upload
	wuUploader(config['ID'], config['PASSWORD'], output, archive=db, 
				includeIndoor=config['includeIndoor'], verbose=config['verbose'])


if __name__ == "__main__":
	main(sys.argv[1:])
