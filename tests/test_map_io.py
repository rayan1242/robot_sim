import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from backend.map_io import save_snapshot
from backend.protocol import encode_cloud,encode_cloud_arrays


class MapIOTests(unittest.TestCase):
    def test_transient_windows_lock_retries_and_publishes_complete_map(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'map.npz';points=np.ones((3,3));colors=np.full((3,3),100,np.uint8)
            replace=Path.replace;calls=[]
            def locked_once(source,target):
                calls.append(source)
                if len(calls)==1:raise PermissionError('simulated sharing violation')
                return replace(source,target)
            with patch.object(Path,'replace',locked_once),patch('backend.map_io.time.sleep'):
                save_snapshot(path,points,colors)
            self.assertEqual(len(calls),2)
            self.assertEqual(encode_cloud(path),encode_cloud_arrays(points,colors))
            self.assertEqual(list(Path(d).glob('map_pending_*')),[])

    def test_persistent_lock_preserves_previous_map_and_memory_encoding(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'map.npz';points=np.ones((3,3));colors=np.zeros((3,3),np.uint8)
            save_snapshot(path,points,colors);previous=path.read_bytes()
            with patch.object(Path,'replace',side_effect=PermissionError('locked')),patch('backend.map_io.time.sleep'):
                with self.assertRaises(PermissionError):save_snapshot(path,points*2,colors,attempts=2)
            self.assertEqual(path.read_bytes(),previous)
            self.assertEqual(encode_cloud_arrays(points*2,colors)[1],3)
            self.assertEqual(list(Path(d).glob('map_pending_*')),[])
