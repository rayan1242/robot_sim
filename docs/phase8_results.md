# Phase 8: simulator foundation

ROS 2 Jazzy and Gazebo Harmonic 8.15.0 installed in existing Ubuntu 24.04 WSL2.
Native WSLg viewer launched; rendered RGB camera output inspected. The world
passes `gz sdf -k` validation. Manual keyboard control, RGB bridge, odometry
bridge and stop watchdog are implemented. See [launch instructions](../sim/README.md).

Measured integration smoke: 47 camera frames, 320x240, 93 odometry messages,
0.3168 m displacement under a brief 0.15 m/s command, followed by zero commands.
Raw results: `data/simulation/smoke/report.json` and `camera.png`.

Cached Depth Anything V2 Small runs under Linux. On the tested simulated image,
known-floor alignment had 6.37% held-out absolute relative error, 1257 training
inliers from 1840 floor samples, 189 occupied and 255 free local grid cells.
These are floor-reference checks, not independent obstacle-depth accuracy.
CPU inference took approximately 2.56 seconds in the recorded check, exceeding
the one-second map freshness requirement. The bounded 20-second automatic trial
published only stop commands. A reliable fit alone does not make a stale map
usable for control. Manual control was restored after the trial.

34 Python tests passed, including four local-map/controller tests. Automatic
collision avoidance, navigation goals, loop closure and simulator/dashboard
integration remain unvalidated or unimplemented. Webcam fusion limitations
remain unresolved; simulation geometry assumptions do not fix them.
