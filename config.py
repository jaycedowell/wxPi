# -*- coding: utf-8 -*-

"""
File for dealing with the configuration of wxPi.py.
"""

import os
import re

from led import LED

__version__ = '0.2'
__all__ = ['CONFIG_FILE', 'loadConfig', '__version__', '__all__']


# Files
## Base path for the various files needed/generated by wxPi.py
_BASE_PATH = os.path.dirname(os.path.abspath(__file__))

## Wunderground Configuration
CONFIG_FILE = os.path.join(_BASE_PATH, 'wxPi.config')


def loadConfig(filename):
	"""
	Read in the configuration file and return a dictionary of the 
	parameters.
	"""
	
	# RegEx for parsing the configuration file lines
	configRE = re.compile(r'\s*:\s*')

	# Initial values
	config = {'verbose': False,
			  'radioPin': 18, 
			  'duration': 60.0, 
			  'includeIndoor': False, 
			  'elevation': 0.0, 
			  'enableBMP085': True, 
			  'redPin': -1, 
			  'yellowPin': -1, 
			  'greenPin': -1}

	# Parse the file
	try:
		fh = open(filename, 'r')
		for line in fh:
			line = line.replace('\n', '')
			## Skip blank lines
			if len(line) < 3:
				continue
			## Skip comments
			if line[0] == '#':
				continue
				
			## Update the dictionary
			key, value = configRE.split(line, 1)
			config[key] = value
			
	except IOError:
		pass
	finally:
		fh.close()
		
	# Convert the values as needed
	## Integer type conversions
	for key in ('radioPin', 'redPin', 'yellowPin', 'greenPin'):
		config[key] = int(config[key])	
	## Float type conversion
	for key in ('duration', 'elevation'):
		config[key] = float(config[key])	
	## Boolean type conversions
	for key in ('verbose', 'includeIndoor', 'enableBMP085'):
		config[key] = bool(config[key])
		
	# Create instances for the LEDs
	config['red'] = LED(config['redPin'])
	config['yellow'] = LED(config['yellowPin'])
	config['green'] = LED(config['greenPin'])
	
	# Remove the LED pins since we have LED instances now
	del config['redPin']
	del config['yellowPin']
	del config['greenPin']
	
	# Done
	return config
