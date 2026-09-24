"""DEXPI-compatible XML and Structured JSON Exporter for Digital P&ID."""

from __future__ import annotations

import json
from typing import Any, Dict, List
import xml.etree.ElementTree as ET
from xml.dom import minidom

from app.db.models import Drawing, DetectedSymbol, Relationship, DetectedLine


class DexpiExporter:
    @staticmethod
    def to_structured_json(drawing: Drawing) -> Dict[str, Any]:
        """Convert a drawing and its topology into structured JSON (Section 5.1 of mockup)."""
        equipment = []
        pumps = []
        valves = []
        instruments = []
        lines = []
        relationships = []

        # Categorize symbols
        for sym in drawing.symbols:
            item = {
                "id": sym.tag or f"sym_{sym.id}",
                "symbol_id": sym.id,
                "type": sym.class_name,
                "bbox": [sym.bbox_x1, sym.bbox_y1, sym.bbox_x2, sym.bbox_y2],
                "confidence": sym.confidence,
            }
            cat = (sym.category or "").lower()
            if "pump" in cat:
                pumps.append(item)
            elif "valve" in cat:
                valves.append(item)
            elif "instrument" in cat:
                instruments.append(item)
            elif "equipment" in cat:
                equipment.append(item)
            else:
                equipment.append(item)

        # Lines
        for line in drawing.lines:
            lines.append({
                "id": f"line_{line.id}",
                "line_type": line.line_type,
                "geometry": line.geometry,
                "confidence": line.confidence,
                "flow_direction": line.flow_direction,
            })

        # Relationships
        symbol_map = {s.id: s for s in drawing.symbols}
        for rel in drawing.relationships:
            from_sym = symbol_map.get(rel.from_symbol_id)
            to_sym = symbol_map.get(rel.to_symbol_id)
            relationships.append({
                "from": from_sym.tag if from_sym and from_sym.tag else f"sym_{rel.from_symbol_id}",
                "to": to_sym.tag if to_sym and to_sym.tag else f"sym_{rel.to_symbol_id}",
                "type": rel.relation_type,
                "line": rel.line_tag or (f"line_{rel.line_id}" if rel.line_id else "-"),
                "confidence": rel.confidence,
            })

        return {
            "drawing_name": drawing.name,
            "image_size": {"width": drawing.width, "height": drawing.height},
            "equipment": equipment,
            "pumps": pumps,
            "valves": valves,
            "instruments": instruments,
            "lines": lines,
            "relationships": relationships,
        }

    @staticmethod
    def to_dexpi_xml(drawing: Drawing) -> str:
        """Convert a drawing and its topology into DEXPI-compatible XML (Section 5.2 of mockup)."""
        root = ET.Element("PipingAndInstrumentationDiagram")
        root.set("xmlns:dexpi", "http://sandbox.dexpi.org/rdl")
        root.set("drawingName", drawing.name)
        if drawing.width and drawing.height:
            root.set("width", str(drawing.width))
            root.set("height", str(drawing.height))

        symbol_map = {s.id: s for s in drawing.symbols}

        # 1. Equipment, Pumps, Valves, Instruments
        for sym in drawing.symbols:
            tag = sym.tag or f"sym_{sym.id}"
            cat = (sym.category or "").lower()

            if "pump" in cat:
                elem = ET.SubElement(root, "Pump")
                elem.set("id", tag)
                elem.set("type", sym.class_name or "Centrifugal Pump")
                name_elem = ET.SubElement(elem, "Name")
                name_elem.text = tag
            elif "valve" in cat:
                elem = ET.SubElement(root, "Valve")
                elem.set("id", tag)
                elem.set("type", sym.class_name or "Gate Valve")
                name_elem = ET.SubElement(elem, "Name")
                name_elem.text = tag
            elif "instrument" in cat:
                elem = ET.SubElement(root, "Instrument")
                elem.set("id", tag)
                elem.set("type", sym.class_name or "PressureIndicator")
                name_elem = ET.SubElement(elem, "Name")
                name_elem.text = tag
            else:
                elem = ET.SubElement(root, "Equipment")
                elem.set("id", tag)
                elem.set("type", sym.class_name or "Equipment")
                name_elem = ET.SubElement(elem, "Name")
                name_elem.text = tag

        # 2. PipeLines
        for line in drawing.lines:
            line_elem = ET.SubElement(root, "PipeLine")
            line_elem.set("id", f"line_{line.id}")
            line_elem.set("lineType", line.line_type)
            if line.flow_direction:
                line_elem.set("flowDirection", line.flow_direction)

        # 3. Connections
        for rel in drawing.relationships:
            from_sym = symbol_map.get(rel.from_symbol_id)
            to_sym = symbol_map.get(rel.to_symbol_id)
            from_tag = from_sym.tag if from_sym and from_sym.tag else f"sym_{rel.from_symbol_id}"
            to_tag = to_sym.tag if to_sym and to_sym.tag else f"sym_{rel.to_symbol_id}"

            conn_elem = ET.SubElement(root, "Connection")
            conn_elem.set("from", from_tag)
            conn_elem.set("to", to_tag)
            conn_elem.set("type", rel.relation_type)
            if rel.line_tag:
                conn_elem.set("line", rel.line_tag)
            elif rel.line_id:
                conn_elem.set("line", f"line_{rel.line_id}")

        # Pretty print XML string
        rough_string = ET.tostring(root, encoding="utf-8")
        parsed = minidom.parseString(rough_string)
        return parsed.toprettyxml(indent="  ")
