"""Evaluation metrics and plots for the 3-class severity model.

Accuracy is misleading here (~75-80 % of collisions are Slight), so the
primary metric is macro-F1, supported by per-class recall and the KSI
false-negative rate: the share of Fatal/Serious collisions predicted as Slight.
Missing a serious collision is the costly error for road-safety triage.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, classification_report,  # noqa: E402
                             confusion_matrix, f1_score, precision_score, recall_score)

from .config import CLASS_NAMES, KSI_CLASSES  # noqa: E402

LABELS = list(range(len(CLASS_NAMES)))


def ksi_false_negative_rate(y_true, y_pred) -> float:
    y_true, y_pred = np.asarray(y_true), np.asarray(y_pred)
    ksi = np.isin(y_true, KSI_CLASSES)
    if not ksi.any():
        return float("nan")
    return float((~np.isin(y_pred[ksi], KSI_CLASSES)).mean())


def compute_metrics(y_true, y_pred, prefix: str = "") -> dict[str, float]:
    recalls = recall_score(y_true, y_pred, labels=LABELS, average=None, zero_division=0)
    precisions = precision_score(y_true, y_pred, labels=LABELS, average=None, zero_division=0)
    f1s = f1_score(y_true, y_pred, labels=LABELS, average=None, zero_division=0)
    m = {
        "macro_f1": f1_score(y_true, y_pred, labels=LABELS, average="macro", zero_division=0),
        "weighted_f1": f1_score(y_true, y_pred, labels=LABELS, average="weighted", zero_division=0),
        "balanced_accuracy": balanced_accuracy_score(y_true, y_pred),
        "accuracy": accuracy_score(y_true, y_pred),
        "ksi_false_negative_rate": ksi_false_negative_rate(y_true, y_pred),
    }
    m["ksi_recall"] = 1 - m["ksi_false_negative_rate"]
    for i, name in enumerate(CLASS_NAMES):
        key = name.lower()
        m[f"recall_{key}"], m[f"precision_{key}"], m[f"f1_{key}"] = recalls[i], precisions[i], f1s[i]
    return {f"{prefix}{k}": round(float(v), 5) for k, v in m.items()}


def report_text(y_true, y_pred) -> str:
    return classification_report(y_true, y_pred, labels=LABELS, target_names=CLASS_NAMES, digits=4, zero_division=0)


def confusion_frame(y_true, y_pred) -> pd.DataFrame:
    cm = confusion_matrix(y_true, y_pred, labels=LABELS)
    return pd.DataFrame(cm, index=[f"true_{c}" for c in CLASS_NAMES], columns=[f"pred_{c}" for c in CLASS_NAMES])


def plot_confusion_matrix(y_true, y_pred, path: Path, title: str) -> Path:
    cm = confusion_matrix(y_true, y_pred, labels=LABELS)
    norm = cm / cm.sum(axis=1, keepdims=True).clip(min=1)
    fig, ax = plt.subplots(figsize=(5.5, 4.6))
    im = ax.imshow(norm, cmap="Blues", vmin=0, vmax=1)
    for i in range(len(LABELS)):
        for j in range(len(LABELS)):
            ax.text(j, i, f"{cm[i, j]:,}\n{norm[i, j]:.1%}", ha="center", va="center",
                    color="white" if norm[i, j] > 0.5 else "black", fontsize=9)
    ax.set_xticks(LABELS, CLASS_NAMES)
    ax.set_yticks(LABELS, CLASS_NAMES)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)
    fig.colorbar(im, ax=ax, fraction=0.046, label="Row-normalised (recall)")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path


def plot_feature_importance(importance: pd.Series, path: Path, top: int = 25) -> Path:
    top_imp = importance.sort_values(ascending=True).tail(top)
    fig, ax = plt.subplots(figsize=(7, 0.28 * len(top_imp) + 1))
    ax.barh(top_imp.index, top_imp.values, color="#2c7fb8")
    ax.set_title(f"Top {len(top_imp)} feature importances")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
