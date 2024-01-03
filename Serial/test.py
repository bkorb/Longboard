import pyvesc
from pyvesc.VESC.messages import GetValues, SetRPM, SetCurrent, SetRotorPositionMode, GetRotorPosition, GetVersion
import serial
import time
import math

# Set your serial port here (either /dev/ttyX or COMX)
serialport = '/dev/ttyACM0'
can_id = 124

def print_bytes(bv):
    print("Start")
    for x in bv:
        #v = int.from_bytes(x, 'big')
        print(x)
    print("End")

def get_values_example():
    with serial.Serial(serialport, baudrate=115200, timeout=0.05) as ser:
        try:
            rpm_1 = pyvesc.encode(SetRPM(2000, can_id=can_id))
            rpm_2 = pyvesc.encode(SetRPM(1000))
            values_1 = pyvesc.encode_request(GetValues(can_id=can_id))
            values_2 = pyvesc.encode_request(GetValues)

            # Optional: Turn on rotor position reading if an encoder is installed
            #ser.write(pyvesc.encode(SetRotorPositionMode(SetRotorPositionMode.DISP_POS_MODE_ENCODER)))
            buf = bytearray(b'')
            t0 = time.time()
            t = 0
            while True:
                # Set the ERPM of the VESC motor
                #    Note: if you want to set the real RPM you can set a scalar
                #          manually in setters.py
                #          12 poles and 19:1 gearbox would have a scalar of 1/228

                t += 0.01
                rpm = int(15000*math.sin(t))
                print(rpm)
                rpm_1 = pyvesc.encode(SetRPM(rpm, can_id=can_id))
                rpm_2 = pyvesc.encode(SetRPM(rpm))
                ser.write(rpm_1)
                ser.write(rpm_2)

                # Request the current measurement from the vesc
                x = time.time()
                if x-t0 > 0.01:
                    #print("log")
                    t0 = x
                    ser.write(values_1)
                    ser.write(values_2)

                # Check if there is enough data back for a measurement
                if ser.in_waiting > 64:
                    buf.extend(ser.read(ser.in_waiting))
                if len(buf) > 64:
                    (response, consumed) = pyvesc.decode(bytes(buf))
                    # Print out the values
                    if response is not None:
                        try:
                            #print(f"RPM: {response.rpm}")
                            my_id = int.from_bytes(response.app_controller_id, "big")
                            #print(f"ID: {my_id}")
                        except Exception:
                            print("Error reading RPM")
                    buf = buf[consumed:]
                time.sleep(0.01)

        except KeyboardInterrupt:
            # Turn Off the VESC
            ser.write(pyvesc.encode(SetCurrent(0)))
            ser.write(pyvesc.encode(SetCurrent(0, can_id=can_id)))


if __name__ == "__main__":
    get_values_example()
