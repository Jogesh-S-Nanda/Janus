"""
    Code for the AG95, roboteq gripper in UR5
    ==================================================================================================
    Author  :   Jogesh S Nanda
    Date    :   10/06/2023
    Version :   1.1
    Notes   :   code is made for AG95 gripper using minimalmodbus library, which is a python library for modbus
                    reference : https://github.com/pyserial/pyserial
                    https://minimalmodbus.readthedocs.io/en/stable/index.html
    Licence:   MIT License
    ==================================================================================================
"""
import minimalmodbus
import serial
import time



"""
==================================================================================================
    Class Gripper : depends on the minimalmodbus library, which is a python library 
    for modbus communication.
==================================================================================================
    functions available are:
        1. read_register    -   read a register from the gripper
        2. write_register   -   write a register to the gripper
        3. debug            - enable debug mode
        4. scale            - scale the value between the min and max values
        5. open             - open the gripper
        6. close            - close the gripper
        7. activate         - activate the gripper
        8. check_state              - check the initial state of the gripper
        9. set_gripping_force       - set the gripping force of the gripper
        10. set_gripping_position   - set the gripping position of the gripper
        11. get_gripping_position   - get the gripping position of the gripper
        12. object_grip             - grip the object using force feedback to the gripper
        13. get_gripper_state       - get the gripper state
==================================================================================================
"""
class Gripper:
    """
    class for the AG95 gripper.
    version: 1.1
    """
    def __init__(self, port, slaveID):
        """
        class constructor.
        :parameter port: port of the serial communication
        :parameter slaveID: to be used for the serial communication
        """
        self.port = port
        self.slaveID = slaveID

        # creating the instance of the instrument
        self.AG95 = minimalmodbus.Instrument(port = self.port, slaveaddress = self.slaveID)

        # serial communication settings
        self.AG95.serial.baudrate = 115200
        self.AG95.serial.bytesize = 8
        self.AG95.serial.parity = serial.PARITY_NONE
        self.AG95.serial.stopbits = 1
        self.AG95.serial.timeout = 1

    def read_register(self, address):
        """
            function to read a register from the Ag95 gripper
        :parameter address:
        :return:
        """
        try:
            value = self.AG95.read_register(address, 0, functioncode=3, signed=False)  # address, number of decimals
            return value

        except Exception as e:
            print(f"Error reading register {address}: {e}")
            return None

    def write_register(self, address, value):
        """
            function to write a register to the Ag95 gripper
        :parameter address:
        :parameter value:
        :return:
        """
        try:
            self.AG95.write_register(address, value, 0, functioncode=6, signed=False)  # address, value, number of decimals
        except Exception as e:
            print(f"Error writing to register {address}: {e}")

    def debug(self):
        """
            function to enable debug mode
        :return:
        """
        self.AG95.debug = True

    def scale(self, value, v_min=0, v_max=1000):
        """
            function to scale the value between the min and max values
        :parameter value:
        :parameter v_min:
        :parameter v_max:
        :return:
        """

        if value > v_max:
            return v_max
        elif value < v_min:
            return v_min
        else:
            # returns the scaled value in hex for serial communication
            return hex(value)

    def open(self):
        """
            function to open the gripper
        :return:
        """
        self.write_register(0x0103, 0x03E8)

    def close(self):
        """
            function to close the gripper
        :return:
        """
        self.write_register(0x0103, 0x0000)

    def activate(self):
        """
            function to activate the gripper
        :return:
        """
        try:
            self.write_register(0x0100, 0xA5)
            print ("Gripper activated")
        except Exception as e:
            print(f"Error activating gripper: {e}")

    def check_state(self):
        """
            function to check the initial state of the gripper
        :return:
        """
        try:
            state = self.read_register(0x0200)
            # checking the initial state of the gripper
            if state == 1:
                print("Gripper is initialized")
                return 1
            else:
                print("Gripper is not initialized")
                return 0

        except Exception as e:
            print(f"Error in reading the initial state: {e}")
            return 0

    def set_gripping_force(self, force = 20):
        """
            function to set the gripping force of the gripper
        :parameter force:
        :return:
        """
        self.write_register(0x0101, self.scale(force, 20, 100))

    def set_gripping_position(self, position = 0):
        """
            function to set the gripping position of the gripper
        :parameter position:
        :return:
        """
        self.write_register(0x0103, self.scale(position, 0, 1000))

    def get_gripping_position(self):
        """
            function to get the gripping position of the gripper
        :return:
        """
        pose = self.read_register(0x0202)
        return pose

    def object_grip(self):
        """
            function to grip the object using force feedback to the gripper
        :return:
        """
        self.close()

        while self.get_gripper_state()[1] == "In motion":
            pass

        pose = self.get_gripping_position()
        self.set_gripping_position(pose)


    def get_gripper_state(self):
        """
            function for gripper states description.
            Different values indicate different states of the gripper. The descriptions of states are as
            follows:
            · 00: Fingers are in motion.
            · 01: Fingers are at reference position. No object detected or an object has been dropped.
            · 02: Fingers have stopped due to object detection.
            · 03: Fingers are at reference position due to an object has been dropped after the gripper caught object.
        """
        state = self.read_register(0x0201)

        # gripper states
        if state == 0:      return 0, "In motion"
        elif state == 1:    return 1, "Reached position"
        elif state == 2:    return 2, "Object caught"
        elif state == 3:    return 3, "Object dropped"
        else:               return 4, "Error"



def main():
    """
    Main method for testing the functionality of the Gripper class.

    This method demonstrates various features of the Gripper class, including
    activation, setting gripping force, position, opening the gripper, and checking
    its state.

    Raises:
        This function
        will raise any exceptions encountered during the execution of the Gripper class methods.
    """
    # code for testing the class and functions
    test_port = "/dev/ttyUSB0"
    test_instrument = Gripper(test_port, 1)

    test_instrument.activate()
    test_instrument.debug()
    test_instrument.check_state()

    test_instrument.set_gripping_force(50)
    test_instrument.set_gripping_position(0)

    test_instrument.open()
    time.sleep(5)
    #test_instrument.close()

    print(test_instrument.get_gripper_state())

    test_instrument.object_grip()

if __name__ == "__main__":
    main()
