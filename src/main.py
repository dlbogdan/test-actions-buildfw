import os
import machine
import utime

# Onboard LED is typically GP25 for Pico, or 'LED' for Pico W
# Use Pin.board.LED if available and targeting Pico W, otherwise use 25
# led_pin = machine.Pin('LED', machine.Pin.OUT) # For Pico W
led_pin = machine.Pin('LED', machine.Pin.OUT)    # For Pico standard

while True:
    led_pin.toggle()
    utime.sleep(1) # Wait for 1 second
    