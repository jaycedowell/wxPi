wxPi
====

A Raspberry Pi-based Oregon Scientific weather station that also supports the 
Bosch BMP085/180 temperature and pressure sensor.

Requirements
------------
 * Python >=2.7 and <3.0
 * sqlite3
 * RPi.GPIO
 * wiringPi
 * a 433 MHz radio with AM demodulation, e.g., QAM-RX3-433

Usage
-----
  1) Wire up the radio, LEDs, and pressure sensor
  
  2) Build the decoder.so extension via 'make'
  
  3) Update the configuration file 'wxPi.config'
  
  4) Run the script via ./wxPi.py

Supported Sensors
-----------------
Oregon Scientific
 * 5D60 - BHTR968 - Indoor temperature/humidity/pressure
 * 2D10 - RGR968  - Rain gauge
 * 3D00 - WGR968  - Anemometer
 * 1D20 - THGR268 - Outdoor temperature/humidity
 * 1D30 - THGR968 - Outdoor temperature/humidity

Bosch
 * BMP085
 * BMP180

The data formats used for these sensors come from:
 * http://www.osengr.org/WxShield/Downloads/OregonScientific-RF-Protocols-II.pdf
 * http://www.disk91.com/2013/technology/hardware/oregon-scientific-sensors-with-raspberry-pi/
 * http://www.mattlary.com/2012/06/23/weather-station-project/
 * https://github.com/tomhartley/AirPi
 * http://learn.adafruit.com/using-the-bmp085-with-raspberry-pi/overview
 * Trial and error

Presumably other sensors that transmit v2.1 or v3.0 sensors are also supported if you 
know the data format.

Breadboard Example
------------------
![wxPi Breadboard](https://github.com/jaycedowell/wxPi/blob/nonRTL/wxPi_breadboard.png)
