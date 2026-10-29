"""Capture local serial boot output; resets the selected board without writing flash."""
import argparse
import pathlib
import time
import serial

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('port')
    p.add_argument('output',type=pathlib.Path)
    p.add_argument('--seconds',type=int,default=30)
    p.add_argument('--no-reset',action='store_true',help='Only listen; do not reset the board')
    a=p.parse_args()
    # Set control lines before opening to avoid accidentally entering download mode.
    connection=serial.Serial(port=None,baudrate=115200,timeout=.2)
    connection.dtr=False;connection.rts=False;connection.port=a.port
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with connection:
        connection.reset_input_buffer()
        if not a.no_reset:
            connection.rts=True;time.sleep(.1);connection.rts=False
        finish=time.monotonic()+a.seconds
        with a.output.open('wb') as f:
            while time.monotonic()<finish:
                data=connection.read(connection.in_waiting or 1)
                if data:
                    f.write(data);f.flush()
    print(a.output.read_bytes().decode('utf-8','replace'))

if __name__=='__main__':main()
