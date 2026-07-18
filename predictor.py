# ml/predictor.py
# Wraps the trained sklearn model for real-time gesture prediction.

import pickle
import numpy as np
from collections import deque
from pathlib import Path
from typing import Optional, Tuple

from utils import get_logger
import config

logger = get_logger(__name__)


class GesturePredictor:
    """
    Loads the trained classifier and label encoder,
    then predicts gesture names from Hand landmark vectors.
    """

    def __init__(self):
        self._model  = None
        self._labels = None
        self._ready  = False
        self._history = deque(maxlen=config.ML_VOTING_WINDOW)
        self._load()

    def _load(self):
        try:
            if Path(config.ML_MODEL_PATH).exists() and Path(config.ML_LABEL_PATH).exists():
                with open(config.ML_MODEL_PATH, "rb") as f:
                    self._model = pickle.load(f)
                with open(config.ML_LABEL_PATH, "rb") as f:
                    self._labels = pickle.load(f)
                self._ready = True
                logger.info("ML model loaded from %s", config.ML_MODEL_PATH)
            else:
                logger.warning("No trained model found. Run ml/trainer.py first.")
        except Exception as e:
            logger.error("Failed to load ML model: %s", e)

    @property
    def ready(self) -> bool:
        return self._ready

    def predict(self, hand) -> Optional[Tuple[str, float]]:
        """
        Predict gesture for a Hand object.

        Returns (gesture_name, confidence) or None if model not ready.
        """
        if not self._ready:
            return None
        try:
            vec = self._landmarks_to_vector(hand)
            X   = np.array([vec], dtype=np.float32)
            if hasattr(self._model, "predict_proba"):
                proba = self._model.predict_proba(X)[0]
                idx   = int(np.argmax(proba))
                conf  = float(proba[idx])
            else:
                idx  = int(self._model.predict(X)[0])
                conf = 1.0

            if conf < config.ML_CONFIDENCE_MIN:
                self._history.clear()
                return None

            label = self._labels.inverse_transform([idx])[0]
            self._history.append((label, conf))
            votes = {}
            confidences = {}
            for name, score in self._history:
                votes[name] = votes.get(name, 0) + 1
                confidences[name] = confidences.get(name, 0.0) + score
            smoothed_label, count = max(votes.items(), key=lambda item: item[1])
            smoothed_conf = confidences[smoothed_label] / count
            if count < config.ML_MIN_VOTES or smoothed_conf < config.ML_CONFIDENCE_MIN:
                return None
            return smoothed_label, smoothed_conf
        except Exception as e:
            logger.debug("Prediction error: %s", e)
            return None

    @staticmethod
    def _landmarks_to_vector(hand) -> list:
        points = np.asarray(hand.landmarks, dtype=np.float32)
        wrist = points[0]
        # Scale by palm size so the feature vector is stable as the user moves
        # toward or away from the webcam. Reflect left hands into the same
        # coordinate system as right hands to avoid training duplicate classes.
        palm_size = float(np.linalg.norm(points[9, :2] - wrist[:2]))
        palm_size = max(palm_size, 1e-4)
        relative = (points - wrist) / palm_size
        if getattr(hand, "handedness", "Right") == "Left":
            relative[:, 0] *= -1.0
        flat  = []
        for x, y, z in relative:
            flat.extend([float(x), float(y), float(z)])
        return flat

    def reset(self):
        """Discard votes after tracking loss or a gesture transition."""
        self._history.clear()
