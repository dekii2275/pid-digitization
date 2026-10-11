# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Optional

from pydantic import BaseModel

from app.models.bounding_box import BoundingBox
from app.models.image_details import ImageDetails

from .symbol_and_text_associated import SymbolAndTextAssociated
from .text_recognized import TextRecognized


class TextDetectionInferenceResponse(BaseModel):
    """
    This class represents the text detection inference results; which includes
    all text detected, and the text and symbols associated on a P&ID image.
    """

    image_url: str
    image_details: ImageDetails
    bounding_box_inclusive: Optional[BoundingBox]
    all_text_list: list[TextRecognized]
    text_and_symbols_associated_list: list[SymbolAndTextAssociated]
