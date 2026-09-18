"""Canonical class order used by the fine-tuned P&ID symbol detector."""

from __future__ import annotations

from typing import Tuple


CLASS_NAMES: Tuple[str, ...] = (
    "Welded gate valve",
    "Plug valve",
    "Globe valve NO",
    "Gate valve NO",
    "Ball valve",
    "Butterfly valve",
    "Manual gate valve",
    "Check valve",
    "Diaphragm valve",
    "Needle valve",
    "Sealing gate valve",
    "Gate valve NC",
    "Globe valve NC",
    "Control valve",
    "Rotary valve NO",
    "Rotary valve NC",
    "Spade blind",
    "Spade close blind (flanged)",
    "Spade open blind (flanged)",
    "Right concentric reducer",
    "Flanged connection",
    "Heating coil tubes",
    "Jacketed pipe",
    "Mid arrow flow direction",
    "Circle valve",
    "Field mounted discrete indicator",
    "Field mounted discrete recorder",
    "Discrete with primary local access",
    "Discrete with auxiliary local access",
    "Solenoid actuator",
    "Shared with primary local access",
    "Shared control logic",
)
