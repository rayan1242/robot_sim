import math
import unittest
import numpy as np

from sim.vision import (camera_matrix,local_grid,velocity_command,CAMERA_HEIGHT,
                        CAMERA_PITCH,HEIGHT,WIDTH)


class SimulationVisionTests(unittest.TestCase):
    def test_stale_and_unknown_maps_do_not_drive(self):
        self.assertEqual(velocity_command(None)[:2],(0,0))
        clear=np.zeros((HEIGHT,WIDTH),np.int8)
        self.assertEqual(velocity_command(clear,fresh=False)[:2],(0,0))
        self.assertEqual(velocity_command(np.full_like(clear,-1))[:2],(0,0))
        self.assertGreater(velocity_command(clear)[0],0)

    def test_obstacle_in_forward_cone_turns_without_advancing(self):
        grid=np.zeros((HEIGHT,WIDTH),np.int8);grid[HEIGHT//2,10]=100
        linear,angular,status=velocity_command(grid)
        self.assertEqual(linear,0);self.assertNotEqual(angular,0)

    def test_known_floor_scale_and_synthetic_obstacle(self):
        matrix=camera_matrix();v,u=np.mgrid[:240,:320]
        denominator=math.sin(CAMERA_PITCH)+math.cos(CAMERA_PITCH)*(v-matrix[1,2])/matrix[1,1]
        z=CAMERA_HEIGHT/np.maximum(denominator,0.01)
        rgb=np.full((240,320,3),120,np.uint8)
        z[70:170,120:200]=0.45;rgb[70:170,120:200]=[30,30,200]
        prediction=(1/z-0.1)/0.7
        grid,report=local_grid(prediction.astype(np.float32),rgb)
        self.assertLess(report['heldout_floor_abs_rel'],0.001)
        self.assertTrue(np.any(grid==100))
        self.assertEqual(velocity_command(grid)[0],0)

    def test_constant_depth_does_not_pass_floor_alignment(self):
        with self.assertRaises(ValueError):
            local_grid(np.ones((240,320),np.float32),np.full((240,320,3),120,np.uint8))
