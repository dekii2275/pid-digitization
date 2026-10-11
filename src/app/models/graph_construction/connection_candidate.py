# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from typing import Optional

from pydantic import BaseModel

from app.models.enums.graph_node_type import GraphNodeType


class ConnectionCandidate(BaseModel):
    node: str = None
    type: GraphNodeType = GraphNodeType.unknown
    distance: Optional[float] = None
    intersection: bool = False
