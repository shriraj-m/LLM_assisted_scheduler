import serial
from time import sleep

ser = serial.Serial('/dev/pts/12', 9600, timeout=1)
while True:
    line = ser.readline().decode('utf-8').rstrip()
    print(line)