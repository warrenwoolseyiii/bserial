#!/usr/bin/env python3

"""bserial.py - A simple command line interface for serial communication

This program provides a command line interface for communicating with a serial port device. It takes two command line arguments, the name of the serial port device and the baud rate of the serial connection. It reads all incoming data from the serial port and prints it to the console, and it also allows the user to send data to the serial port by typing it into the console.

Usage:
  bserial.py [-h] -p PORT -b BAUD

Options:
  -h, --help            Show this help message and exit
  -p PORT, --port=PORT  Name of the serial port device
  -b BAUD, --baud=BAUD  Baud rate of the serial connection

Example:
  bserial.py -p /dev/ttyUSB0 -b 9600

"""

import argparse
import threading
import sys
from serial import Serial

def read_serial(serial_port):
    """Read data from the serial port and print it to the console.

    This function reads data from the specified serial port and prints it to the console.
    It runs in a separate thread so that it does not block the main thread.

    Args:
        serial_port (Serial): The Serial object representing the serial port to read from.

    """
    while True:
        if serial_port.in_waiting > 0:
            # Read all available data from the serial port and print it to the console
            data = serial_port.read_all().decode()
            sys.stdout.write(data)
            sys.stdout.flush()

def main(args):
    """Main function for the bserial program.

    This function is the main entry point for the bserial program. It takes command line arguments
    specifying the serial port device and baud rate, and then opens a connection to the device and
    starts a separate thread to read data from the serial port. It also allows the user to send data
    to the serial port by typing it into the console.

    Args:
        args (Namespace): A Namespace object containing the command line arguments.

    """
    try:
        # Open a connection to the specified serial port
        serial_port = Serial(args.port, args.baud)
        print(f"Connected to serial port {args.port} at {args.baud} baud")

        # Start a separate thread to read data from the serial port
        thread = threading.Thread(target=read_serial, args=(serial_port,), daemon=True)
        thread.start()

        # Read input from the console and send it to the serial port
        while True:
            input_data = input()
            serial_port.write(input_data.encode())
    except Exception as e:
        print(f"Failed to connect to serial port {args.port} at {args.baud} baud")
        print(e)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read from and write to a serial port')
    parser.add_argument('-p', '--port', help='Serial port name')
    parser.add_argument('-b', '--baud', type=int, help='Baud rate')
    args = parser.parse_args()

    if args.port is None or args.baud is None:
        parser.print_usage()
        sys.exit(1)

    main(args)