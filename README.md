wxPi
====

A Raspberry Pi-based Oregon Scientific weather station

Requirements
------------
 * Python >=2.7 and <3.0
 * sqlite3
 * librtlsdr from http://sdr.osmocom.org/trac/wiki/rtl-sdr

Usage
-----
  1) Build the decoder.so extension via 'make'
  
  2) Update the configuration file 'wxPi.config'
  
  3) Run the script via ./wxPi.py

Supported Sensors
-----------------
 * 5D60 - BHTR968 - Indoor temperature/humidity/pressure
 * 2D10 - RGR968  - Rain gauge
 * 3D00 - WGR968  - Anemometer
 * 1D20 - THGR268 - Outdoor temperature/humidity
 * 1D30 - THGR968 - Outdoor temperature/humidity

The data formats used for these sensors come from:
 * http://www.osengr.org/WxShield/Downloads/OregonScientific-RF-Protocols-II.pdf
 * http://www.disk91.com/2013/technology/hardware/oregon-scientific-sensors-with-raspberry-pi/
 * http://www.mattlary.com/2012/06/23/weather-station-project/
 * Trial and error

Presumably other sensors that transmit v2.1 or v3.0 sensors are also supported if you 
know the data format.
