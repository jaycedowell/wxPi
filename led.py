"""
Module for controlling LEDs hooked into the GPIO ports on a Rasberry Pi.
"""

import time
import threading

__version__ = '0.3'
__all__ = ['GPIOLED', '__version__', '__all__']


class GPIOLED(object):
	"""
	Class for controlling an LED via GPIO.
	"""
	
	def __init__(self, pin):
		"""
		Initialize the class with a GPIO pin number and make sure that the 
		specified as been exported via /sys/class/gpio/export and that it 
		is marked for output.
		"""
	
		# GPIO pin
		self.pin = int(pin)
		
		# State information (for polling)
		self.state = 'unknown'
		
		# Thread information for blinking
		self.thread = None
		self.alive = threading.Event()
		
		# Setup
		if self.pin > 0:
			try:	
				# Export
				fh = open('/sys/class/gpio/export', 'w')
				fh.write(str(self.pin))
				fh.flush()
				fh.close()
				
				# Direction
				fh = open('/sys/class/gpio/gpio%i/direction' % self.pin, 'w')
				fh.write('out')
				fh.flush()
				fh.close()
				
			except IOError:
				pass
				
	def getState(self):
		"""
		Get the state of the LED.
		"""
		
		return self.state
		
	def on(self):
		"""
		Turn the LED on.
		"""
		
		if self.pin > 0:
			try:
				fh = open('/sys/class/gpio/gpio%i/value' % self.pin, 'w')
				fh.write('1')
				fh.close()
			
				self.state = 'on'
			except IOError:
				pass
			
	def off(self):
		"""
		Turn the LED off.
		"""
	
		if self.pin > 0:
			try:
				fh = open('/sys/class/gpio/gpio%i/value' % self.pin, 'w')
				fh.write('0')
				fh.close()
				
				self.state = 'off'
			except IOError:
				pass
				
	def blink(self, blinkPeriod=0.25):
		"""
		Set the LED to blinking with the specified interval in seconds.   This function
		starts the LED blinking if it isn't already and stops it if it is.
		"""
		
		self.period = float(blinkPeriod)
		
		if self.thread is not None:
			self._stop()
			self.state = 'off'
		else:
			self._start()
			self.state = 'blink'
			
	def _start(self):
		"""
		Start the blinking thread.
		"""
		
		if self.pin > 0:
			if self.thread is None:
				self.thread = threading.Thread(target=self._cycle, name='blink%i' % self.pin)
				self.thread.setDaemon(1)
				self.alive.set()
				self.thread.start()
				
	def _stop(self):
		"""
		Stop the blinking thread.
		"""
		
		if self.pin > 0:
			if self.thread is not None:
				self.alive.clear()
				self.thread.join()
				self.thread = None
				self.off()
				
	def _cycle(self):
		"""
		Background function for controlling the LED's blinking.
		"""
		
		while self.alive.isSet():
			# On
			try:
				fh = open('/sys/class/gpio/gpio%i/value' % self.pin, 'w')
				fh.write('1')
				fh.close()
			except IOError:
				pass
				
			if self.alive.isSet():
				time.sleep(self.period)
				
			# Off
			try:
				fh = open('/sys/class/gpio/gpio%i/value' % self.pin, 'w')
				fh.write('0')
				fh.close()
			except IOError:
				pass
				
			if self.alive.isSet():
				time.sleep(self.period)
