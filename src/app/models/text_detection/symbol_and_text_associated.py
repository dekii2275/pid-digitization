# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Optional

from app.models.symbol_detection.label import Label


class SymbolAndTextAssociated(Label):
    """
    Class that represents the symbol detected properties and the text associated within the symbol
    """

    text_associated: Optional[str]
