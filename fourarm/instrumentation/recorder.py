"""Episode recorder: saves the overhead camera to a video during any run.

Usage in a script:
    from instrumentation.recorder import Recorder
    cell.recorder = Recorder("out/episode.mp4", every=8)
    ... run as normal ...
    cell.recorder.close()

Cell.tick calls recorder.grab(scene) automatically when a recorder is set.
`every=8` at the 120 Hz sim rate gives a 15 fps video.

Encoding uses OpenCV if available (ships with Isaac Sim). If not, frames are
saved as numbered PNGs plus a ready-made ffmpeg command to assemble them.
"""

import os

import numpy as np

try:
    import cv2
    _HAVE_CV2 = True
except ImportError:
    _HAVE_CV2 = False


class Recorder:
    def __init__(self, out_path, every=8, camera="table_cam", fps=None):
        self.out_path = out_path
        self.every = every
        self.camera = camera
        self.fps = fps or max(1, round(120 / every))
        self._count = 0
        self._writer = None
        self._frame_dir = None
        self._frames = 0
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    def _to_uint8(self, rgb):
        arr = rgb[..., :3]
        if arr.dtype != np.uint8:
            arr = ((arr * 255).clip(0, 255) if arr.max() <= 1.0
                   else arr.clip(0, 255)).astype(np.uint8)
        return arr

    def grab(self, scene):
        self._count += 1
        if self._count % self.every:
            return
        rgb = scene[self.camera].data.output["rgb"][0].detach().cpu().numpy()
        frame = self._to_uint8(rgb)
        if _HAVE_CV2:
            if self._writer is None:
                h, w = frame.shape[:2]
                self._writer = cv2.VideoWriter(
                    self.out_path, cv2.VideoWriter_fourcc(*"mp4v"),
                    self.fps, (w, h))
            self._writer.write(cv2.cvtColor(frame, cv2.COLOR_RGB2BGR))
        else:
            if self._frame_dir is None:
                self._frame_dir = self.out_path + "_frames"
                os.makedirs(self._frame_dir, exist_ok=True)
            from PIL import Image
            Image.fromarray(frame).save(
                os.path.join(self._frame_dir, f"{self._frames:06d}.png"))
        self._frames += 1

    def close(self):
        if self._writer is not None:
            self._writer.release()
            print(f"[recorder] wrote {self._frames} frames to {self.out_path}")
        elif self._frame_dir is not None:
            print(f"[recorder] wrote {self._frames} PNGs to {self._frame_dir}")
            print(f"[recorder] assemble: ffmpeg -framerate {self.fps} "
                  f"-i {self._frame_dir}/%06d.png -c:v libx264 "
                  f"-pix_fmt yuv420p {self.out_path}")
        else:
            print("[recorder] no frames captured")
