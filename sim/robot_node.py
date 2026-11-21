"""Camera-only local map/controller. Manual by default; avoidance is simulation-only."""
import argparse
import json
import os
from pathlib import Path
import sys
import threading
import time

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from rclpy.clock import Clock,ClockType
from geometry_msgs.msg import Twist
from nav_msgs.msg import OccupancyGrid
from sensor_msgs.msg import Image
from std_msgs.msg import String

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sim.check_sim import image_bgr
from sim.vision import local_grid,velocity_command,RESOLUTION,WIDTH,HEIGHT


class Robot(Node):
    def __init__(self,args):
        super().__init__("mono_robot_controller")
        self.args=args;self.lock=threading.Lock();self.stop=threading.Event()
        self.latest=None;self.result=None;self.manual=(0.,0.,0.);self.frames=0
        self.create_subscription(Image,"/camera/image_raw",self.image,qos_profile_sensor_data)
        self.create_subscription(Twist,"/teleop_cmd",self.teleop,10)
        self.velocity=self.create_publisher(Twist,"/cmd_vel",10)
        self.map_pub=self.create_publisher(OccupancyGrid,"/local_occupancy",1)
        self.status_pub=self.create_publisher(String,"/mono/status",10)
        self.create_timer(0.1,self.tick,clock=Clock(clock_type=ClockType.STEADY_TIME))
        self.output=args.output;self.output.mkdir(parents=True,exist_ok=True)
        self.log=(self.output/"controller.jsonl").open("w")
        self.last_log=0;self.last_map=-1
        self.worker=threading.Thread(target=self.process,daemon=True);self.worker.start()
    def image(self,message):
        image=image_bgr(message)
        with self.lock:
            self.frames+=1
            self.latest=(self.frames,time.monotonic(),image,message.header.stamp)
    def teleop(self,message):
        self.manual=(max(-0.15,min(0.15,message.linear.x)),max(-0.6,min(0.6,message.angular.z)),time.monotonic())
    def process(self):
        model=None
        if self.args.mode=="avoid":
            try:
                import torch
                torch.set_num_threads(2)
                from perception.depth import DepthEstimator
                model=DepthEstimator(device=self.args.depth_device,local_files_only=True)
                self.get_logger().info(f"Depth inference running on {model.device}")
            except Exception as exc:
                self.get_logger().error(f"Depth inference initialization failed: {exc}")
                with self.lock:self.result={"reliable":False,"error":str(exc),"received":0,"sequence":-1}
                return
        previous=-1
        while not self.stop.wait(0.01):
            with self.lock:frame=self.latest
            if frame is None or frame[0]==previous:continue
            sequence,received,image,stamp=frame;previous=sequence
            cv2.imwrite(str(self.output/"camera_latest.png"),image)
            result={"sequence":sequence,"received":received,"stamp":stamp,"reliable":False,"grid":None}
            if model is not None:
                try:
                    prediction=model.predict(image)
                    grid,diagnostic=local_grid(prediction,image)
                    result.update(grid=grid,reliable=True,diagnostic=diagnostic)
                    np.savez_compressed(self.output/"local_map_latest.npz",grid=grid)
                    from perception.depth import colorize_depth
                    cv2.imwrite(str(self.output/"relative_depth_latest.png"),colorize_depth(prediction))
                except Exception as exc:result["error"]=str(exc)
            with self.lock:self.result=result
    def tick(self):
        now=time.monotonic()
        with self.lock:result=self.result;frame=self.latest
        fresh=frame is not None and now-frame[1]<1.0
        if self.args.mode=="manual":
            linear,angular,updated=self.manual
            if not fresh or now-updated>0.5:linear=angular=0.
            reason="manual" if fresh else "stopped_stale_camera"
        else:
            result_fresh=result is not None and now-result["received"]<1.0
            linear,angular,reason=velocity_command(result.get("grid") if result else None,
                                                reliable=bool(result and result["reliable"]),fresh=result_fresh)
        command=Twist();command.linear.x=linear;command.angular.z=angular;self.velocity.publish(command)
        if result and result["reliable"] and result["sequence"]!=self.last_map:
            grid=OccupancyGrid();grid.header.frame_id="base_link";grid.header.stamp=result["stamp"]
            grid.info.resolution=RESOLUTION;grid.info.width=WIDTH;grid.info.height=HEIGHT
            grid.info.origin.position.y=-HEIGHT*RESOLUTION/2;grid.info.origin.orientation.w=1.
            grid.data=result["grid"].reshape(-1).tolist();self.map_pub.publish(grid);self.last_map=result["sequence"]
        if self.args.mode=="avoid" and result and not result_fresh:
            reason="stopped_depth_unavailable" if result["sequence"] == -1 else "stopped_stale_depth"
        status={"mode":self.args.mode,"state":reason,"camera_frames":self.frames,"linear_mps":linear,"angular_rps":angular,
                "map_age_seconds":now-result["received"] if result else None,
                "frame_age_seconds":now-frame[1] if frame else None,
                "map_reliable":bool(result and result["reliable"]),"error":result.get("error") if result else None,
                "diagnostic":result.get("diagnostic") if result else None}
        message=String();message.data=json.dumps(status);self.status_pub.publish(message)
        if now-self.last_log>=0.5:
            self.log.write(message.data+"\n");self.log.flush();self.last_log=now
            (self.output/"status.json").write_text(json.dumps(status,indent=2))
    def close(self):
        self.stop.set();self.worker.join(timeout=3)
        if rclpy.ok():
            for _ in range(5):self.velocity.publish(Twist());time.sleep(0.02)
        self.log.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode",choices=["manual","avoid"],default="manual")
    parser.add_argument("--depth-device",choices=["cuda","cpu"],default=os.environ.get("SIM_DEPTH_DEVICE","cuda"))
    parser.add_argument("--output",type=Path,default=Path("data/simulation/controller"))
    parser.add_argument("--duration",type=float,default=0)
    args=parser.parse_args()
    if args.depth_device not in ("cuda","cpu"):
        parser.error("SIM_DEPTH_DEVICE must be cuda or cpu")
    rclpy.init();node=Robot(args);started=time.monotonic()
    try:
        while rclpy.ok() and (args.duration<=0 or time.monotonic()-started<args.duration):rclpy.spin_once(node,timeout_sec=0.1)
    except KeyboardInterrupt:pass
    finally:
        node.close();node.destroy_node()
        if rclpy.ok():rclpy.shutdown()


if __name__=="__main__":main()
