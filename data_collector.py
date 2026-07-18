# ml/data_collector.py
# Collect training samples for the ML gesture classifier.
# Run this script directly to record landmark vectors labelled with a gesture name.
#
# Usage:
#   python ml/data_collector.py --gesture THUMB_UP --samples 200

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import csv
import argparse
import time
import cv2
import numpy as np
from pathlib import Path

from cv.hand_tracker import HandTracker
from cv.camera_thread import CameraThread
from utils import get_logger
import config

logger = get_logger(__name__)

DATASET_PATH = os.path.join(config.MODELS_DIR, "gesture_dataset.csv")
LANDMARK_COUNT = 21 * 3  # x, y, z per landmark


def landmarks_to_vector(hand) -> list:
    """Return the same translation/scale/handedness-invariant vector as inference."""
    lms = np.asarray(hand.landmarks, dtype=np.float32)
    wrist = lms[0]
    palm_size = max(float(np.linalg.norm(lms[9, :2] - wrist[:2])), 1e-4)
    lms = (lms - wrist) / palm_size
    if hand.handedness == "Left":
        lms[:, 0] *= -1.0
    flat = []
    for x, y, z in lms:
        flat.extend([float(x), float(y), float(z)])
    return flat


def collect(gesture_name: str, n_samples: int = 200, interval: float = 0.08):
    cam     = CameraThread()
    tracker = HandTracker(max_hands=1)

    if not cam.start():
        logger.error("Cannot open camera.")
        return

    # Prepare CSV
    write_header = not Path(DATASET_PATH).exists()
    f   = open(DATASET_PATH, "a", newline="")
    csv_writer = csv.writer(f)
    if write_header:
        header = ["label"] + [f"f{i}" for i in range(LANDMARK_COUNT)]
        csv_writer.writerow(header)

    collected = 0
    last_sample_at = 0.0
    logger.info("Collecting %d samples for gesture '%s'.", n_samples, gesture_name)
    print(f"\n[DATA COLLECTOR] Get ready — collecting '{gesture_name}'. "
          f"Press 'q' to quit early.\n")
    time.sleep(2)

    while collected < n_samples:
        frame = cam.read()
        if frame is None:
            continue

        annotated, hands = tracker.process(frame)

        now = time.perf_counter()
        if (hands and hands[0].score >= config.CONTROL_HAND_MIN_CONF
                and now - last_sample_at >= interval):
            vec = landmarks_to_vector(hands[0])
            if np.isfinite(vec).all():
                csv_writer.writerow([gesture_name] + vec)
                collected += 1
                last_sample_at = now

        # Visual feedback
        cv2.putText(annotated, f"{gesture_name}  {collected}/{n_samples}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 100), 2)
        cv2.imshow("Data Collector — press q to quit", annotated)
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

    f.close()
    cam.stop()
    tracker.close()
    cv2.destroyAllWindows()
    logger.info("Collection complete: %d samples saved to %s", collected, DATASET_PATH)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--gesture", required=True,
                        help="Gesture label to collect (e.g. THUMB_UP)")
    parser.add_argument("--samples", type=int, default=200,
                        help="Number of samples to collect (default 200)")
    parser.add_argument("--interval", type=float, default=0.08,
                        help="Minimum seconds between samples (default 0.08)")
    args = parser.parse_args()
    collect(args.gesture, args.samples, args.interval)
