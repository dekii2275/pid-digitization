"""Tiled, source-coordinate YOLO inference for uploaded P&ID raster images."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class YoloDetection:
    """One checkpoint prediction in original-image pixel coordinates."""

    class_id: int
    class_name: str
    confidence: float
    bbox: tuple[float, float, float, float]


def category_for_class(class_name: str) -> str:
    """Keep the trained class verbatim while providing an optional UI group."""

    name = class_name.casefold()
    if "valve" in name or "blind" in name:
        return "Valve"
    if any(token in name for token in ("indicator", "recorder", "access", "logic", "actuator")):
        return "Instrument"
    if any(token in name for token in ("pipe", "connection", "reducer", "coil", "arrow")):
        return "Line"
    return "Other"


def bbox_iou(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    left, top = max(first[0], second[0]), max(first[1], second[1])
    right, bottom = min(first[2], second[2]), min(first[3], second[3])
    intersection = max(0.0, right - left) * max(0.0, bottom - top)
    if intersection <= 0:
        return 0.0
    first_area = max(0.0, first[2] - first[0]) * max(0.0, first[3] - first[1])
    second_area = max(0.0, second[2] - second[0]) * max(0.0, second[3] - second[1])
    union = first_area + second_area - intersection
    return intersection / union if union else 0.0


def class_aware_nms(detections: Iterable[YoloDetection], iou_threshold: float) -> list[YoloDetection]:
    """Merge overlapping tile predictions without suppressing different classes."""

    grouped: dict[int, list[YoloDetection]] = defaultdict(list)
    for detection in detections:
        grouped[detection.class_id].append(detection)

    kept: list[YoloDetection] = []
    for candidates in grouped.values():
        remaining = sorted(candidates, key=lambda item: item.confidence, reverse=True)
        while remaining:
            best = remaining.pop(0)
            kept.append(best)
            remaining = [item for item in remaining if bbox_iou(best.bbox, item.bbox) < iou_threshold]
    return sorted(kept, key=lambda item: item.confidence, reverse=True)


class YoloSymbolDetector:
    """Loads the trained checkpoint once and detects every class on all image tiles."""

    def __init__(
        self,
        weights_path: Path,
        device: str = "auto",
        tile_size: int = 1024,
        overlap: float = 0.25,
        confidence: float = 0.15,
        model_iou: float = 0.70,
        merge_iou: float = 0.50,
    ) -> None:
        self.weights_path = weights_path
        self.device = None if device == "auto" else device
        self.tile_size = tile_size
        self.overlap = overlap
        self.confidence = confidence
        self.model_iou = model_iou
        self.merge_iou = merge_iou
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is not None:
            return self._model
        if not self.weights_path.is_file():
            raise FileNotFoundError(f"YOLO weights not found: {self.weights_path}")
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError("YOLO runtime is not installed. Install the ultralytics dependency.") from exc
        self._model = YOLO(str(self.weights_path))
        return self._model

    def _tile_positions(self, length: int) -> list[int]:
        if length <= self.tile_size:
            return [0]
        stride = max(1, round(self.tile_size * (1 - self.overlap)))
        final = length - self.tile_size
        positions = list(range(0, final + 1, stride))
        if positions[-1] != final:
            positions.append(final)
        return positions

    @staticmethod
    def _class_names(model: Any) -> dict[int, str]:
        names = getattr(model, "names", {})
        if isinstance(names, dict):
            return {int(key): str(value) for key, value in names.items()}
        if isinstance(names, (list, tuple)):
            return {index: str(value) for index, value in enumerate(names)}
        return {}

    @staticmethod
    def _read_image(source_path: Path) -> np.ndarray:
        encoded = np.fromfile(source_path, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError(f"Unable to decode uploaded image: {source_path.name}")
        return image

    def detect_image(self, source_path: Path) -> list[YoloDetection]:
        """Detect all checkpoint classes and return boxes in source-image coordinates."""

        image = self._read_image(source_path)
        height, width = image.shape[:2]
        model = self._load_model()
        names = self._class_names(model)
        detections: list[YoloDetection] = []

        for y in self._tile_positions(height):
            for x in self._tile_positions(width):
                tile = image[y : y + self.tile_size, x : x + self.tile_size]
                result = model.predict(
                    source=tile,
                    imgsz=self.tile_size,
                    conf=self.confidence,
                    iou=self.model_iou,
                    device=self.device,
                    save=False,
                    verbose=False,
                )[0]
                if result.boxes is None or len(result.boxes) == 0:
                    continue
                for box, score, class_id in zip(
                    result.boxes.xyxy.cpu().tolist(),
                    result.boxes.conf.cpu().tolist(),
                    result.boxes.cls.cpu().tolist(),
                ):
                    class_index = int(class_id)
                    x1, y1, x2, y2 = box
                    detections.append(
                        YoloDetection(
                            class_id=class_index,
                            class_name=names.get(class_index, f"class_{class_index}"),
                            confidence=float(score),
                            bbox=(
                                max(0.0, min(float(width), x + float(x1))),
                                max(0.0, min(float(height), y + float(y1))),
                                max(0.0, min(float(width), x + float(x2))),
                                max(0.0, min(float(height), y + float(y2))),
                            ),
                        )
                    )
        return class_aware_nms(detections, self.merge_iou)
