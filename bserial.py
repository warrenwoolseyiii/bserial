#!/usr/bin/env python3
import sys
import getopt
import serial
import select

currentString = ''

def printArgHelp():
    print('amrConsole.py -p <port> -b <baud>')

def parsingStateMachine(nextByte, ser):
    global currentString

    if nextByte == b'\n':
        print(currentString)
        currentString = ''
    else:
        try:
            currentString += nextByte.decode("utf_8")
        except UnicodeDecodeError:
            print('Caught unicode error: ', currentString)
            currentString = ''

def runSerialParser( ser ):
    numBytesToRead = ser.inWaiting()
    while numBytesToRead > 0:
        parsingStateMachine(ser.read(1), ser)
        numBytesToRead = numBytesToRead - 1

def runConsole(ser):
    runSerialParser(ser)
    while sys.stdin in select.select([sys.stdin], [], [], 0)[0]:
        line = sys.stdin.readline()
        #parseInput(line, ser)
        ser.write(line.strip('\r\n').encode('utf-8'))

def main(argv):
    comPort = ''
    baudRate = 38400

    ## Check the args
    if len(argv) < 2:
        printArgHelp()
        sys.exit(2)

    try:
        opts, args = getopt.getopt(argv,"hp:b:",["port=","baud="])
    except getopt.GetoptError:
        printArgHelp()
        sys.exit(2)

    ## Parse the args
    for opt, arg in opts:
        if opt == '-h':
            printArgHelp()
            sys.exit()
        elif opt in ("-p", "--port"):
            comPort = arg
        elif opt in ("-b", "--baud"):
            baudRate = arg

    ## Open the serial port
    ser = serial.Serial(
        port=comPort,
        baudrate=baudRate,
        parity=serial.PARITY_NONE,
        stopbits=serial.STOPBITS_ONE,
        bytesize=serial.EIGHTBITS,
        xonxoff=0,
        rtscts=False,
        dsrdtr=False
    )

    ser.close()
    ser.open()
    ser.isOpen()
    ser.flushInput()
    ser.flushOutput()

    #printUsage()

    while True:
        runConsole(ser)

if __name__ == "__main__":
    main(sys.argv[1:])