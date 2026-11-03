"""
Shared webcam + FaceLandmarker pipeline for head yaw/pitch, used by both
the main tracker loop and the calibration wizard so the mediapipe setup
only lives in one place.
"""

from collections import namedtuple

import cv2
import mediapipe as mp
import numpy as np
from mediapipe.tasks import python as mp_tasks_python
from mediapipe.tasks.python import vision as mp_vision

ASSUMED_MS_PER_FRAME = 33  # only used to build a monotonically increasing timestamp

PoseFrame = namedtuple(
    "PoseFrame",
    ["frame", "found", "yaw", "pitch", "raw_yaw", "raw_pitch", "face_landmarks"],
)


def rotation_matrix_to_euler_degrees(R):
    """Returns (pitch, yaw, roll) in degrees."""
    sy = np.sqrt(R[0, 0] ** 2 + R[1, 0] ** 2)
    singular = sy < 1e-6
    if not singular:
        pitch = np.arctan2(R[2, 1], R[2, 2])
        yaw = np.arctan2(-R[2, 0], sy)
        roll = np.arctan2(R[1, 0], R[0, 0])
    else:
        pitch = np.arctan2(-R[1, 2], R[1, 1])
        yaw = np.arctan2(-R[2, 0], sy)
        roll = 0.0
    return np.degrees(pitch), np.degrees(yaw), np.degrees(roll)


class HeadPoseStream:
    """Opens the webcam + FaceLandmarker and yields smoothed yaw/pitch per frame."""

    def __init__(self, model_path, cam_index=0, yaw_sign=1, pitch_sign=1, ema_alpha=0.3):
        self._cap = cv2.VideoCapture(cam_index)
        if not self._cap.isOpened():
            raise RuntimeError(f"Could not open camera index {cam_index}")

        base_options = mp_tasks_python.BaseOptions(model_asset_path=model_path)
        options = mp_vision.FaceLandmarkerOptions(
            base_options=base_options,
            running_mode=mp_vision.RunningMode.VIDEO,
            num_faces=1,
            output_face_blendshapes=False,
            output_facial_transformation_matrixes=True,
        )
        self._landmarker = mp_vision.FaceLandmarker.create_from_options(options)

        self._yaw_sign = yaw_sign
        self._pitch_sign = pitch_sign
        self._ema_alpha = ema_alpha
        self._smoothed_yaw = None
        self._smoothed_pitch = None
        self._frame_idx = 0

    def read(self):
        """Returns a PoseFrame, or None if the camera gave up a frame."""
        ok, frame = self._cap.read()
        if not ok:
            return None

        frame = cv2.flip(frame, 1)  # mirror view, feels natural
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

        timestamp_ms = self._frame_idx * ASSUMED_MS_PER_FRAME
        self._frame_idx += 1
        result = self._landmarker.detect_for_video(mp_image, timestamp_ms)

        if not result.facial_transformation_matrixes:
            return PoseFrame(frame, False, self._smoothed_yaw, self._smoothed_pitch, None, None, None)

        matrix = np.array(result.facial_transformation_matrixes[0])
        pitch, yaw, _roll = rotation_matrix_to_euler_degrees(matrix[:3, :3])
        # Cast off numpy scalar types here so nothing downstream (e.g. the
        # calibration wizard's JSON save) trips over a non-JSON-serializable
        # numpy.float32 leaking out of this pipeline.
        yaw = float(yaw) * self._yaw_sign
        pitch = float(pitch) * self._pitch_sign

        self._smoothed_yaw = yaw if self._smoothed_yaw is None else (
            self._ema_alpha * yaw + (1 - self._ema_alpha) * self._smoothed_yaw
        )
        self._smoothed_pitch = pitch if self._smoothed_pitch is None else (
            self._ema_alpha * pitch + (1 - self._ema_alpha) * self._smoothed_pitch
        )

        face_landmarks = result.face_landmarks[0] if result.face_landmarks else None
        return PoseFrame(
            frame, True, self._smoothed_yaw, self._smoothed_pitch, yaw, pitch, face_landmarks
        )

    def close(self):
        self._cap.release()
        self._landmarker.close()
