"""ROS integration smoke test: RGB frames and a short bounded drive, then stop."""
import argparse
import json
import math
from pathlib import Path
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from sensor_msgs.msg import Image


def image_bgr(message):
    if message.encoding not in ("rgb8", "bgr8"):
        raise ValueError(f"Unsupported camera encoding: {message.encoding}")
    data=np.frombuffer(message.data,dtype=np.uint8).reshape(message.height,message.step)
    image=data[:,:message.width*3].reshape(message.height,message.width,3)
    return cv2.cvtColor(image,cv2.COLOR_RGB2BGR) if message.encoding=="rgb8" else image.copy()


class Check(Node):
    def __init__(self,output):
        super().__init__("mono_sim_check")
        self.images=0; self.positions=[]; self.output=output
        self.sub_image=self.create_subscription(Image,"/camera/image_raw",self.image,qos_profile_sensor_data)
        self.sub_odom=self.create_subscription(Odometry,"/odom",self.odom,10)
        self.commands=self.create_publisher(Twist,"/teleop_cmd",10)
    def image(self,message):
        self.images+=1
        if self.images==1:
            image=image_bgr(message)
            self.output.mkdir(parents=True,exist_ok=True)
            cv2.imwrite(str(self.output/"camera.png"),image)
            self.image_size=[message.width,message.height]
    def odom(self,message):
        point=message.pose.pose.position
        self.positions.append([point.x,point.y])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path,default=Path("data/simulation/smoke"))
    args=parser.parse_args()
    rclpy.init();node=Check(args.output)
    try:
        deadline=time.monotonic()+60
        while time.monotonic()<deadline and (node.images<3 or len(node.positions)<3):
            rclpy.spin_once(node,timeout_sec=0.1)
        if node.images<3 or not node.positions:
            raise RuntimeError(f"Simulation not ready: images={node.images}, odometry={len(node.positions)}")
        start=node.positions[-1]
        command=Twist();command.linear.x=0.15
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            node.commands.publish(command)
            rclpy.spin_once(node,timeout_sec=0.05)
        end=node.positions[-1]
        distance=math.dist(start,end)
        report={"camera_frames_received":node.images,"camera_size_wh":node.image_size,
                "odometry_messages":len(node.positions),"command_linear_mps":0.15,
                "odometry_displacement_m":distance,"motion_verified":distance>0.05,
                "note":"Odometry is used only for integration verification, not camera-only obstacle control"}
        args.output.mkdir(parents=True,exist_ok=True)
        (args.output/"report.json").write_text(json.dumps(report,indent=2))
        print(json.dumps(report,indent=2))
        if distance<=0.05:
            raise RuntimeError("Robot did not move enough under velocity commands")
    finally:
        for _ in range(5):
            node.commands.publish(Twist());rclpy.spin_once(node,timeout_sec=0.05)
        node.destroy_node();rclpy.shutdown()


if __name__=="__main__":main()
