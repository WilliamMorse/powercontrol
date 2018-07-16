"""
Convenence class to drive electromagnetic coils with the powersupplies.

Uses the supplies in constant current mode.
"""
import powercontrol.powersupply as powersupply


class Coil:
    """parent class for a coil that is attached to a BK powersupply."""

    def __init__(self, address: str, field_gain: float) -> None:
        """
        Initialize a Coil object.

        Parameters
        ----------
        address: str
            String representing the device identifier of the power supply.
        field_gain: float
            Value representing the strength of the center of the field at
            1 amp of current. Units are in Tesla/Amp

        Returns
        -------
        None

        """
        # assign the correct port address to a powersupply objectsupply
        self.supply = powersupply.PowerSupply(address)

        # calibration dependant data:
        self.field_gain = field_gain.n  # T/A
        # power supply current command limits
        self.maxPowerSupplyCurrent = 0.9990  # A
        self.minPowerSupplyCurrent = 0.001  # A

        # Maximum and minimum possible field that can be produced by the coil.
        self.appliedMaxField = self.field_gain * self.maxPowerSupplyCurrent
        self.appliedMinField = self.field_gain * self.minPowerSupplyCurrent

        # innitalize field value containers.
        # Amps
        self.current = self.supply.get_current()

        # Total field
        self.coil_field = self.current * self.field_gain

    def set_coil_field(self, field_value: float) -> None:
        """
        Set the magnetic field of the coil to a fixed value.

        Parameters
        ----------
        field_value: float
            Value representing the strength of the center of the field.
            Units are in Tesla.

        Returns
        -------
        None

        """
        # prevents setting the coil with the same value
        if field_value != self.coil_field:
            # calculate the current from the field value
            current = field_value / self.field_gain

            # fomat the large coil current to the same precision as
            # the powersupply
            self.current = float('%5.4f' % current)

            # with the formatted current we can recalculate the coil_field
            self.coil_field = self.current * self.field_gain

            # make sure the current is in AMPS
            self.supply.set_current(self.current)
        else:
            print('coil already set to %s' % self.coil_field)

    def get_coil_field(self) -> float:
        """
        Get the magnetic field of the coil.

        Useful for when the power supply was adusted manually and we want to
        read the new field value.

        Parameters
        ----------
        None

        Returns
        -------
        coil_field: float
            Value of the magnetic field at its center, in Tesla.

        """
        # query the current
        self.current = self.supply.get_current()

        # use the new current to update the field value:
        self.coil_field = self.current * self.field_gain

        return self.coil_field


# TODO: Depreciated. Revise.
class CoilWithCorrection(Coil):
    """
    coil with additional correction coil controlled by the labjack
    """
    def __init__(self,
                 powersupplyAddress,
                 field_gain,
                 dacName,
                 smallCoilFieldGain):

        Coil.__init__(self, powersupplyAddress, field_gain)

        # the DAC to which the adustment coil is connected
        self.dacName = dacName
        self.smallCoilFieldGain = smallCoilFieldGain  # T/A
        self.voltageGain = 250  # opAmp current source gain in (V/A)
        self.dacVoltage = 0.0  # store the voltage to write to the DAC

        # use this value to measure the smallest deveation avalable from the
        # large powersupplies
        self.minPowerSupplyCurrentStep = 0.0001  # Amps
        # and the field now gets divided into two coils
        self.smallCoilField = 0.0  # portion of the total field for the small coils
        self.net_coil_field = self.coil_field + self.smallCoilField

    def setSmallCoilField(self, fieldValue):
        """
        sets the adustmetn coils to the specified value.
        the adustment coils only work in one direction and add to the field
        of the large coils.
        due to the constraints of the labjack serial link, this function
        only sets the local variable 'smallCoilVoltage' which can later
        be passed to the labjack with the other DAC setting to minimize
        comunication time
        """
        # update the field container
        self.smallFieldValue = fieldValue

        # calculate the current from the field gain
        current = fieldValue / self.smallCoilFieldGain.n

        # V = I*R the formula for the op-amp current supply circuit.
        self.dacVoltage = current * self.voltageGain

    def setField(self, fieldValue):
        """
        set both the small and large coils.
        use the large coils to get in range of the desired value,
        and the small ones to precisely set the field.
        """
        # calculate the smallest field that the large coil can produce with the
        # powersupplies. This will be the unit that we use to calculate
        # avalable ranges.
        minimumcoil_fieldStep = self.minPowerSupplyCurrentStep * self.field_gain
        # total range of the small coil.
        # o--|--|--|--|--|--|--|->| the small ticks are the minimumcoil_fieldStep
        # o  |--|--|**|--|--|       this is the range of the dac after removing the voltage clamping band of the opAmp (stay away from the voltage rails)
        #  pick the ** for the middle of our field.
        # usable +- range of the small coil (total range is 3 steps)
        # o  {--|--|**|--|--}       Curly braces are the trigger points where we want to renormalize
        smallCoilFieldRange = 2.5 * minimumcoil_fieldStep # allow this to go althe way to the clamping band
        # o  |--|--|**|--|--|       Distance from the left side is 3.5 smallest divisions
        coil_fieldOffset = minimumcoil_fieldStep * 3.5
        # the extra .5 above is to hack the rounding in the current function so that it truncates instead of rounding :P
        smallCoilFieldOffse = minimumcoil_fieldStep * 3.0

        # with this in mind let's split the field btween the large and small coils
        # the large coil is easy we just subtract the field offset and let the
        # powersupply.PowerSupply.current() function round up or down with format %5.1f

        # set the large coils only if we are out of range of the dacs
        maximumChangeInField = coil_fieldOffset + smallCoilFieldRange
        minimumChangeInField = coil_fieldOffset - smallCoilFieldRange

        self.smallFieldValue = (fieldValue - self.coil_field)

        if (self.smallFieldValue > maximumChangeInField
           or self.smallFieldValue < minimumChangeInField):
            # renormalize!
            # set the large coil to the field value minus the field that we
            # will add with the adustment coils
            self.setcoil_field(fieldValue - coil_fieldOffset)

        # for the small coil, we need to first provide the field offset
        # setcoil_field recalculates the true field contribution
        # of the large coil so we can simply subtract that from our desired
        #  field value, and set the small coil field.
        self.setSmallCoilField(fieldValue - self.coil_field)
        # We do NOT want to run the labjack code here because its better to
        # give it both coil values at once in the xyzFieldControl module.

        # update the total coil field for the next call
        self.net_coil_field = fieldValue
