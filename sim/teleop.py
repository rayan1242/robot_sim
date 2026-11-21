"""Terminal WASD control; commands expire when keys are released."""
import select
import os
import sys
import termios
import tty
import time

import rclpy
from geometry_msgs.msg import Twist


def main():
    rclpy.init();node=rclpy.create_node("mono_keyboard");publisher=node.create_publisher(Twist,"/teleop_cmd",10)
    original=termios.tcgetattr(sys.stdin)
    linear=angular=0.;last=0.
    print("Keep THIS TERMINAL focused. W/S move | A/D turn | Space stop | Q quit.",flush=True)
    print("Hold a key to keep moving. Gazebo's window does not receive these controls.",flush=True)
    previous=None
    try:
        tty.setcbreak(sys.stdin.fileno())
        while rclpy.ok():
            if select.select([sys.stdin],[],[],0.05)[0]:
                key=os.read(sys.stdin.fileno(),1).decode(errors='ignore').lower();last=time.monotonic()
                if key=='q':break
                linear,angular={'w':(0.15,0.),'s':(-0.15,0.),'a':(0.,0.5),'d':(0.,-0.5)}.get(key,(0.,0.))
            if time.monotonic()-last>0.65:linear=angular=0.
            state=(linear,angular)
            if state!=previous:
                print(f"\rCommand: forward={linear:+.2f} m/s turn={angular:+.2f} rad/s    ",end='',flush=True)
                previous=state
            command=Twist();command.linear.x=linear;command.angular.z=angular;publisher.publish(command)
            rclpy.spin_once(node,timeout_sec=0)
    finally:
        if rclpy.ok():publisher.publish(Twist())
        termios.tcsetattr(sys.stdin,termios.TCSADRAIN,original);node.destroy_node()
        if rclpy.ok():rclpy.shutdown()
        print()


if __name__=="__main__":main()
