import argparse
import serial
import sys
import threading


def read_serial(serial_port):
    while True:
        try:
            if serial_port.in_waiting > 0:
                data = serial_port.read(serial_port.in_waiting)
                sys.stdout.write(data.decode('ascii'))
        except serial.SerialException:
            print('Failed to read data from serial port')
            sys.exit(1)


def read_console(serial_port):
    while True:
        try:
            data = sys.stdin.read(1)
            if data:
                serial_port.write(data.encode('ascii'))
        except serial.SerialException:
            print('Failed to write data to serial port')
            sys.exit(1)


def main(args):
    try:
        serial_port = serial.Serial(args.port, args.baud)
    except serial.SerialException:
        print(
            f'Failed to connect to serial port {args.port} at {args.baud} baud')
        sys.exit(1)

    t1 = threading.Thread(target=read_serial, args=[serial_port])
    t2 = threading.Thread(target=read_console, args=[serial_port])

    t1.start()
    t2.start()

    t1.join()
    t2.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Read from and write to a serial port')
    parser.add_argument('-p', '--port', help='Serial port name')
    parser.add_argument('-b', '--baud', type=int, help='Baud rate')
    args = parser.parse_args()

    if args.port is None or args.baud is None:
        parser.print_usage()
        sys.exit(1)

    main(args)
