#include "Python.h"
#include <iostream>
#include <stdlib.h>
#include <errno.h>
#include <signal.h>
#include "wiringPi.h"

#include "RCSwitch.h"
#include "RcOok.h"

using namespace std;


static int do_exit = 0;

/*
  sighandler - Signal handler for the read433 function
*/

static void sighandler(int signum)
{
	fprintf(stderr, "Signal caught, exiting!\n");
	do_exit = 1;
}


/* 
   callbackFunction - Function for getting data out of read433 and back into Python
*/

static PyObject *callbackFunc = NULL;


/*
  read433 - Function for reading directly from an RTL-SDR and returning a list of
  Manchester decoded bits.
*/

static PyObject *read433(PyObject *self, PyObject *args, PyObject *kwds) {
	PyObject *output, *cbf, *arglist, *result;
	PyGILState_STATE gstate;
	long inputPin;
	struct sigaction sigact;
	char message[512];
	
	static char *kwlist[] = {"inputPin", "callback", NULL};
	if( !PyArg_ParseTupleAndKeywords(args, kwds, "iO:set_callback", kwlist, &inputPin, &cbf) ) {
		PyErr_Format(PyExc_RuntimeError, "Invalid parameters");
		return NULL;
	}
	
	// Validate the input
	if (!PyCallable_Check(cbf)) {
		PyErr_SetString(PyExc_TypeError, "callback parameter must be callable");
        return NULL;
    }
    
    // Setup the callback
    Py_XINCREF(cbf);         	/* Add a reference to new callback */
    Py_XDECREF(callbackFunc);  /* Dispose of previous callback */
    callbackFunc = cbf;       	/* Remember new callback */
	
	// Setup the 433 MHz receiver
	if(wiringPiSetupSys() == -1) {
		PyErr_Format(PyExc_RuntimeError, "Cannot initialize the wiringPi library");
		return NULL;
   	}
   	RCSwitch *rc = new RCSwitch(inputPin,-1);
   	
   	// Setup the signal handler	so that we can exit the callback function
	sigact.sa_handler = sighandler;
	sigemptyset(&sigact.sa_mask);
	sigact.sa_flags = 0;
	sigaction(SIGINT, &sigact, NULL);
	sigaction(SIGTERM, &sigact, NULL);
	sigaction(SIGQUIT, &sigact, NULL);
	sigaction(SIGPIPE, &sigact, NULL);
	
	// Go
	while ( !do_exit ) {
		//// Check for a message
		if ( rc->OokAvailable() ) {
			rc->getOokCode(message);
			
			//// Preserve the state
			gstate = PyGILState_Ensure();
			
			//// Send to the callback
			arglist = Py_BuildValue("(s)", message);
			result = PyObject_CallObject(callbackFunc, arglist);
			Py_DECREF(arglist);
			if (result == NULL) {
    				return NULL; /* Pass error back */
			}
			Py_DECREF(result);
			
			//// Resume the state
			PyGILState_Release(gstate);		
		}
		
		//// Wait a bit (~1 ms)
		usleep(1000);
	}
	
	// Close out wiringPi
	rc->disableReceive();
		
	// Return
	output = Py_True;
	Py_INCREF(output);
	return output;
}

PyDoc_STRVAR(read433_doc, \
"Read in the data from a 433 MHz receiver device and perform Manchester\n\
decoding, and return a list of strings for each packet received that is\n\
suitable for identifying Oregon Scientific v2.1 and v3.0 sensor data.\n\
\n\
Inputs:\n\
  * inputPin - GPIO pin on the Raspberry Pi to use\n\
  * callback - callback function for parsing the packets\n\
\n\
Outputs:\n\
 * True upon completion\n\
\n\
Based on:\n\
 * http://www.osengr.org/WxShield/Downloads/OregonScientific-RF-Protocols-II.pdf\n\
 * http://www.disk91.com/2013/technology/hardware/oregon-scientific-sensors-with-raspberry-pi/\n\
 * https://github.com/daveblackuk/RPI_Oregan.git\n\
");
 
 
/*
  Module Setup - Function Definitions and Documentation
*/

static PyMethodDef DecoderMethods[] = {
	{"read433", (PyCFunction) read433, METH_VARARGS | METH_KEYWORDS, read433_doc}, 
	{NULL, NULL, 0, NULL}
};

PyDoc_STRVAR(Decoder_doc, \
"Module to read in and Manchester decode Oregon Scientific v2.1 and v3.0 weather\n\
station data.");


/*
  Module Setup - Initialization
*/

PyMODINIT_FUNC initdecoder(void) {
	PyObject *m;

	// Module definitions and functions
	m = Py_InitModule3("decoder", DecoderMethods, Decoder_doc);
	
	// Version and revision information
	PyModule_AddObject(m, "__version__", PyString_FromString("0.2"));
}
