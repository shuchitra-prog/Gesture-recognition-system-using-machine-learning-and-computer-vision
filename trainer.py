# ml/trainer.py
# Train gesture classifiers from collected CSV data.
# Supports RandomForest, SVM, and KNN. Compares accuracy and saves best model.
#
# Usage:  python ml/trainer.py

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pickle
import numpy as np
import pandas as pd
from pathlib import Path

from sklearn.model_selection import train_test_split
from sklearn.ensemble import RandomForestClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.preprocessing import LabelEncoder
from sklearn.metrics import classification_report, accuracy_score

from utils import get_logger
import config

logger = get_logger(__name__)

DATASET_PATH = os.path.join(config.MODELS_DIR, "gesture_dataset.csv")
MODEL_PATH   = config.ML_MODEL_PATH
LABEL_PATH   = config.ML_LABEL_PATH


def load_data():
    if not Path(DATASET_PATH).exists():
        raise FileNotFoundError(f"Dataset not found: {DATASET_PATH}\n"
                                "Run ml/data_collector.py first.")
    df = pd.read_csv(DATASET_PATH)
    if "label" not in df.columns:
        raise ValueError("Dataset must contain a 'label' column.")
    X  = df.drop("label", axis=1).values.astype(np.float32)
    y  = df["label"].values
    if X.shape[1] != 63:
        raise ValueError(f"Expected 63 landmark features, found {X.shape[1]}.")
    if not np.isfinite(X).all():
        raise ValueError("Dataset contains non-finite landmark values.")
    classes, counts = np.unique(y, return_counts=True)
    if len(classes) < 2:
        raise ValueError("Collect samples for at least two gesture classes.")
    if counts.min() < 5:
        raise ValueError("Each gesture class needs at least five valid samples.")
    logger.info("Loaded %d samples, %d classes.", len(X), len(np.unique(y)))
    return X, y


def train():
    X, y = load_data()

    # Encode string labels → integers
    le = LabelEncoder()
    y_enc = le.fit_transform(y)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y_enc, test_size=0.2, random_state=42, stratify=y_enc
    )

    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=300, random_state=42, class_weight="balanced_subsample"
        ),
        "SVM":          SVC(kernel="rbf", C=10, gamma="scale", probability=True,
                            class_weight="balanced"),
        "KNN":          KNeighborsClassifier(n_neighbors=7),
    }

    results = {}
    best_name, best_model, best_acc = None, None, 0.0

    print("\n" + "="*60)
    print("  GESTURE CLASSIFIER TRAINING")
    print("="*60)

    for name, clf in models.items():
        clf.fit(X_train, y_train)
        preds = clf.predict(X_test)
        acc   = accuracy_score(y_test, preds)
        results[name] = acc
        print(f"\n── {name} ──")
        print(classification_report(y_test, preds, target_names=le.classes_))
        print(f"   Accuracy: {acc:.4f}")

        if acc > best_acc:
            best_acc   = acc
            best_name  = name
            best_model = clf

    print("\n" + "="*60)
    print(f"  Best model: {best_name}  (accuracy {best_acc:.4f})")
    print("="*60 + "\n")

    # Save best model + label encoder
    with open(MODEL_PATH, "wb") as f:
        pickle.dump(best_model, f)
    with open(LABEL_PATH, "wb") as f:
        pickle.dump(le, f)

    logger.info("Model saved to %s", MODEL_PATH)
    return results


if __name__ == "__main__":
    train()
