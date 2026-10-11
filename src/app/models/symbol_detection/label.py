# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Optional

from app.models.bounding_box import BoundingBox


class Label(BoundingBox):
    """
    This class represents a tagged label of a symbol detected on a P&ID image.
    """

    id: int
    label: str
    score: Optional[float]
