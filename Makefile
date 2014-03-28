CFLAGS = $(shell python-config --cflags)
LDFLAGS = $(shell python-config --ldflags) -lwiringPi

decoder.so: decoder.o RCSwitch.o RcOok.o
	$(CXX) -o decoder.so decoder.o RCSwitch.o RcOok.o -lm -shared $(LDFLAGS)

decoder.o: decoder.cpp
	$(CXX) -c $(CFLAGS) -fPIC -o decoder.o decoder.cpp -O3

RCSwitch.o: RCSwitch.cpp
	$(CXX) -c $(CFLAGS) -fPIC -o RCSwitch.o RCSwitch.cpp -O3
	
RcOok.o: RcOok.cpp
	$(CXX) -c $(CFLAGS) -fPIC -o RcOok.o RcOok.cpp -O3

clean:
	rm -rf RCSwitch.o RcOok.o decoder.o decoder.so
