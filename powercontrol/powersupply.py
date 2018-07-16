"""General purpose python interface for BK1739 powersupples."""

import time
import serial
import re

from typing import Union


class PowerSupply:
    """Class representing a BK1739 powersupply."""

    def __init__(self, portAddress: str) -> None:
        """
        Init the internal variables specific to the powersupply.

        Parameters
        ----------
        portAddress : str
            A string representing the address of the powersupply's connection
            to the host computer.

        Returns
        -------
        None

        """
        # the string that tells the self.serial library to open the
        # correct port
        self.portAddress = portAddress
        self.portOpen = False

    def open_port(self) -> None:
        """
        Open this object's serial port for communication.

        Parameters
        ----------
        None

        Returns
        -------
        None

        """
        # open the self.serial port with the settings for the bk-1739 supplies
        self.ser = serial.Serial(port=self.portAddress,
                                 baudrate=9600,
                                 parity=serial.PARITY_NONE,
                                 stopbits=serial.STOPBITS_ONE,
                                 bytesize=serial.EIGHTBITS)

        self.ser.isOpen()
        self.portOpen = True

    def close_port(self) -> None:
        """
        Close this object's serial port.

        This action clears our input buffer, and the port will need to be
        reopened before reading or writing to the device can occur.

        Parameters
        ----------
        None

        Returns
        -------
        None

        """
        # clear the buffer on close
        self.ser.reset_input_buffer()
        self.ser.close()
        self.portOpen = False

    def _write(self, command: bytearray) -> Union[bytearray, float, str]:
        """
        Write arbitrary commands to the powersupply.

        Parameters
        ----------
        command : bytearray
            A command string in a bytearray formatted in UTF-8.

        Returns
        -------
        out : bytearray xor float xor str
            Depending on the command sent to the powersupply, it will return
            a string (typicaly an error message), a number representing a
            voltage or current value, or nothing.

        """
        # first write the command to the port
        # add the return char to the command bytearray
        self.ser.write(command + b'\r')

        # now wait for the powersupply to respond
        time.sleep(0.05)  # make this longer if you're getting errors

        # read the return message
        out = bytearray()  # empty bytearray to fill from the input buffer

        # while we have bytes wating in the buffer to read
        while self.ser.inWaiting() > 0:
            # detect the stop bit from the powersupply which happens to be
            # '\x11'. The start bit is: '\x13'.
            bufferByte = self.ser.read()
            # messages always start with '\x13' so we can wait for that char
            # and parse out the message
            if bufferByte == b'\x13':
                # read past the start bit
                bufferByte = self.ser.read()
                while bufferByte != b'\x11' and bufferByte != b'\r':
                    # We are inside the message
                    out += bufferByte
                    bufferByte = self.ser.read()  # read the next byte

                # clean out the input buffer after reading the message
                self.ser.reset_input_buffer()

        # check to see if we have any bytes in the byte array
        # if we don't, then that means that we just set the current and the
        # powersupply is just telling us that it's finished setting the current
        # with the return bytes
        if not len(out):
            return out

        out = out.decode("utf-8")  # switch from type bytearray to string

        # now we want to format the output to be a float if we have a number.
        temp = re.search(r'\d+\.\d', out)  # look for a number in out

        if bool(temp):  # if we find a numbers in the string,
            # put them together and cast them as a float.
            out = float(temp.group())

        # In all cases, return
        return out

    def parseErrorMessages(self, message: str) -> None:
        """
        Raise an exception if message corresponds to a known error type.

        Parameters
        ----------
        message : str
            A possible error sent by the powersupply.

        Returns
        -------
        None

        """
        if message == 'Syntax Error':
            raise Exception("Syntax Error. Command not a number" +
                            " or value too high for the power supply")
        elif message == 'Out Of Range':
            raise Exception("Input number out of range! (Likly too small." +
                            " Minimum is 0.01V or 0.1mA)")
        else:
            raise Exception("Strange message receved: %s" % message)

    def check_mode(self) -> str:
        """
        Test to see the current mode of the object.

        Parameters
        ----------
        None

        Returns
        -------
        out: str
            Either the string 'CV' if constant voltage or 'CC' if the mode is
            constant current.

        """
        out = self._write(bytearray('STAT?', 'utf-8'))
        # handle if we get unexpected values for the mode
        if out != 'CV' and out != 'CC':
            self.parseErrorMessages(out)

        # In all cases
        return out

    def _automated_open(self) -> bool:
        """
        Open a port if it isn't opened already.

        Parameters
        ----------
        None

        Returns
        -------
        initial_port_state: bool
            the state of self.portOpen before we attempted to open a port.

        """
        initial_port_state = self.portOpen
        if not initial_port_state:
            self.open_port()
        return initial_port_state

    def _automated_close(self, initial_port_state: bool) -> None:
        """
        Close a port if it was closed before.

        Parameters
        ----------
        initial_port_state: bool
            Old value of self.portOpen

        Returns
        -------
        None

        """
        if not initial_port_state and self.portOpen:
            self.close_port()

    def get_identifier(self) -> str:
        """
        Get powersupply identification information.

        Parameters
        ----------
        None

        Returns
        -------
        out : str
            Usually "B+K PRECISION 1739 Revision x.x"

        """
        return self._write(bytearray('IDN?', 'utf-8'))

    def set_voltage(self, voltage_value: float) -> None:
        """
        Set the voltage of this object.

        Parameters
        ----------
        voltage_value: float
            Value in volts to set the voltage at. Can acommodate up to two
            digits after the decimal place. Minimum precision is 0.01V.
            Maximum value is 99.99V.

        Returns
        -------
        None

        """
        initial_port_state = self._automated_open()
        # formats the voltage to have 5 chars and 2 digits before and after
        # the decimal
        voltage = str('%05.2f' % voltage_value)
        # format and write to the port
        out = self._write(bytearray('VOLT ' + voltage, 'utf-8'))

        # if we get anything back, there is an error.
        if len(out):
            self.parseErrorMessages(out)

        self._automated_close(initial_port_state)

    def get_voltage(self) -> float:
        """
        Get the current of this object.

        Parameters
        ----------
        None

        Returns
        -------
        out: float
            Floating-point value of the voltage of this object in volts.

        """
        initial_port_state = self._automated_open()

        if self.check_mode() != 'CV':
            raise Exception("Incorrect mode!" +
                            " Supply is in constant current mode.")

        # querry the voltage from the powersupply.
        # write command to query current powersupply voltage
        out = self._write(bytearray('VOLT?', 'utf-8'))

        # Handle errors.
        if type(out) != float:
            self.parseErrorMessages(out)

        self._automated_close(initial_port_state)

        return out

    def get_current(self) -> float:
        """
        Get the current of this object.

        Parameters
        ----------
        None

        Returns
        -------
        out: float
            Floating-point value of the current of this object in amps.

        """
        # Open a connection if we aren't connected yet.
        initial_port_state = self._automated_open()

        out = self._write(bytearray('CURR?', 'utf-8'))

        # Handle errors.
        if type(out) != float:
            self.parseErrorMessages(out)

        # convert output back to AMPS from milliamps
        out *= 1e-3

        self._automated_close(initial_port_state)
        return out

    def set_current(self, current_value: float) -> None:
        """
        Set the current of this object.

        Parameters
        ----------
        current_value: float
            Value in amps to set the current at. Can acommodate up to four
            digits after the decimal place. Minimum precision is 0.1mA.
            Maximum value is 0.9999

        Returns
        -------
        None

        """
        # handles the port state so we can leave it open if it is open
        initial_port_state = self._automated_open()

        # make sure the supply is in constant current mode.
        if self.check_mode() != 'CC':
            raise Exception("Incorrect mode!" +
                            " Supply is in constant voltage mode.")

        # change from amps to milliamps because that's what the
        # powersupply wants.
        current_value *= 1e3

        print(current_value)

        # sets the setCurrent to have 5 chars and 3 digits before and
        # 1 digit after the decimal
        current = str('%05.1f' % current_value)

        # format and write to the port
        out = self._write(bytearray('CURR ' + current, 'utf-8'))

        # if we get anything back, there was an error.
        if len(out):
            self.parseErrorMessages(out)

        self._automated_close(initial_port_state)
