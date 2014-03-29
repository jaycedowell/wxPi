"""
Module for controlling LEDs hooked into the GPIO ports on a Rasberry Pi.
"""

import time
import threading

__version__ = '0.1'
__all__ = ['setOutput', 'on', 'off', 'blinkOn', 'blinkOff', '__version__', '__all__']


# Internal state dictionary used by the blinkOn/blinkOff functions
_state = {}


def setOutput(pin):
	"""
	Export the specified GPIO pin and set it to output.
	"""
	
	pin = int(pin)
	# Export
	fh = open('/sys/class/gpio/export', 'w')
	fh.write(str(pine))
	fh.close()
	# Direction
	fh = open('/sys/class/gpio/gpio%i/direction' % pin, 'w')
	fh.write('out')
	fh.close()


def on(pin):
	"""
	Set the LED on the specified pin to the 'on' state.
	"""
	
	pin = int(pin)
	fh = open('/sys/class/gpio/gpio%i/value' % pin, 'w')
	fh.write('1')
	fh.close()


def off(pin):
	"""
	Set the LED on the specified pin to the 'off' state.
	"""
	
	pin = int(pin)
	fh = open('/sys/class/gpio/gpio%i/value' % pin, 'w')
        fh.write('0')
        fh.close()


class _blink(object):
	"""
	Class that uses a seperate control thread to blink a GPIO-attached
	LED on and off.
	"""	

	def __init__(self, pin, blinkPeriod=0.25):
		"""
		Initialize the object with the GPIO pin number and the duration
		of the on and off states in seconds.
		"""
		
		self.pin = int(pin)
		self.period = float(blinkPeriod)
		
		self.thread = None
		self.alive = threading.Event()
		
	def start(self):
		"""
		Start the blinking.
		"""
		
		if self.thread is not None:
			self.stop()
			       
		self.thread = threading.Thread(target=self.cycle, name='blink%i' % self.pin)
		self.thread.setDaemon(1)
		self.alive.set()
		self.thread.start()
		
	def stop(self):
		"""
		Stop the blinking.
		"""
		
		if self.thread is not None:
			self.alive.clear()
			self.thread.join()
			self.thread = None
			off(self.pin)
			
	def cycle(self):
		"""
		Background function for controlling the LED's state.
		"""
		
		while self.alive.isSet():
			on(self.pin)
			if self.alive.isSet():
				time.sleep(self.period)
			off(self.pin)
			if self.alive.isSet():
				time.sleep(self.period)


def blinkOn(pin, blinkPeriod=0.25):
	"""
	Start the LED on the specified GPIO blinking with the provided cadence.
	"""
	
	# Pin
	pin = int(pin)
	
	# Are we already blinking?
	try:
		_state[pin].stop()
	except KeyError:
		pass
		
	# Start
	_state[pin] = _blink(pin, blinkPeriod=blinkPeriod)
	_state[pin].start()


def blinkOff(pin):
	"""
	Stop the LED on the specified GPIO from blinking.
	"""
	
	# Pin
	pin = int(pin)
	
	# Are we already blinking?
	try:
		_state[pin].stop()
		del _state[pin]
	except KeyError:
		pass
