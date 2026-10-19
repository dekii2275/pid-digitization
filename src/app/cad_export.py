"""Export editable CAD geometry; raster scans are not embedded or vector traced."""

from __future__ import annotations

import hashlib
import io
import json

import ezdxf
from ezdxf.enums import TextEntityAlignment

from app.drawing_editor import cad_kind, line_points

APP_ID = "VPI_PID"
LAYERS = {
    "PID_EQUIPMENT": 3,
    "PID_INSTRUMENTS": 6,
    "PID_PIPES": 4,
    "PID_SIGNALS": 2,
    "PID_TAGS": 7,
    "PID_TEXT": 7,
    "PID_CONNECTIONS": 8,
    "PID_CONNECTORS": 5,
}


def safe_text(value):
    # MTEXT backslashes/braces are formatting instructions. Keep OCR literal.
    return str(value).replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def set_identity(entity, source, generation, kind, id_):
    metadata = json.dumps(
        {
            "drawing_id": source["drawing_id"],
            "page_number": source["page_number"],
            "generation": generation,
            "kind": kind,
            "id": str(id_),
        },
        ensure_ascii=True,
    )
    entity.set_xdata(
        APP_ID, [(1000, metadata[index : index + 240]) for index in range(0, len(metadata), 240)]
    )


def build_block(doc, kind, width, height, text_height):
    signature = hashlib.sha256(
        f"{kind}:{width:.12g}:{height:.12g}:{text_height:.12g}".encode()
    ).hexdigest()[:12]
    name = f"PID_{kind.upper()}_{signature}"
    if name in doc.blocks:
        return name
    block = doc.blocks.new(name)
    left, right, bottom, top = -width / 2, width / 2, -height / 2, height / 2
    if kind in {"pump", "instrument"}:
        radius = min(width, height) * 0.42
        block.add_circle((0, 0), radius)
        block.add_line((-radius, 0), (radius, 0))
        if kind == "pump":
            block.add_lwpolyline(
                [(radius * 0.35, radius * 0.35), (radius * 0.8, 0), (radius * 0.35, -radius * 0.35)]
            )
    elif kind in {"valve", "globe_valve"}:
        block.add_lwpolyline(
            [(left, bottom), (right, top), (right, bottom), (left, top)], close=True
        )
        if kind == "globe_valve":
            radius = min(width, height) * 0.14
            block.add_hatch(color=0).paths.add_edge_path().add_arc((0, 0), radius, 0, 360)
    elif kind == "check_valve":
        block.add_lwpolyline([(left, bottom), (right, 0), (left, top)], close=True)
        block.add_line((right, bottom), (right, top))
    elif kind == "connector":
        shoulder = right - width * 0.2
        block.add_lwpolyline(
            [(left, bottom), (shoulder, bottom), (right, 0), (shoulder, top), (left, top)],
            close=True,
        )
    else:
        block.add_lwpolyline(
            [(left, bottom), (right, bottom), (right, top), (left, top)], close=True
        )
        if kind == "vessel":
            block.add_line((left, height * 0.25), (right, height * 0.25))
            block.add_line((left, -height * 0.25), (right, -height * 0.25))
    block.add_attdef(
        "TAG",
        (left, bottom - text_height * 1.5),
        dxfattribs={"height": text_height, "layer": "PID_TAGS"},
    )
    block.add_attdef("EID", (0, 0), dxfattribs={"height": text_height, "flags": 1})
    return name


def scene_to_dxf(scene, generation):
    source = scene["source"]
    settings = scene["cad_settings"]
    scale = settings["units_per_pixel"]
    height = source["height"]
    doc = ezdxf.new("R2010")
    doc.units = {"unitless": 0, "mm": 4, "inch": 1}[settings["units"]]
    doc.appids.new(APP_ID)
    for name, color in LAYERS.items():
        doc.layers.new(name, dxfattribs={"color": color})
    doc.linetypes.add(
        "PID_SIGNAL_DASHED",
        pattern=[12 * scale, 8 * scale, -4 * scale],
        description="P&ID signal reference: dashed",
    )
    doc.layers.get("PID_SIGNALS").dxf.linetype = "PID_SIGNAL_DASHED"
    model = doc.modelspace()

    def point(x, y):
        return x * scale, (height - y) * scale

    for symbol in scene["symbols"]:
        kind = cad_kind(symbol)
        width, symbol_height = symbol["width"] * scale, symbol["height"] * scale
        text_height = max(4, min(24, symbol["height"] * 0.18)) * scale
        block_name = build_block(doc, kind, width, symbol_height, text_height)
        insert = model.add_blockref(
            block_name,
            point(symbol["x"] + symbol["width"] / 2, symbol["y"] + symbol["height"] / 2),
            dxfattribs={
                "rotation": -symbol.get("rotation", 0),
                "layer": "PID_INSTRUMENTS"
                if kind == "instrument"
                else "PID_CONNECTORS"
                if kind == "connector"
                else "PID_EQUIPMENT",
            },
        )
        insert.add_auto_attribs({"TAG": symbol.get("tag", ""), "EID": symbol["id"]})
        set_identity(insert, source, generation, "symbol", symbol["id"])
    for text in scene["texts"]:
        content = text.get("text", "").replace("\r\n", "\n").replace("\r", "\n")
        if "\n" in content or len(content) > 240:
            # DXF MTEXT character height applies to each line. Its standard
            # baseline spacing is 5/3 of that height, not the whole OCR box.
            line_count = content.count("\n") + 1
            char_height = text["height"] * 0.8 / (1 + (line_count - 1) * 5 / 3)
            entity = model.add_mtext(
                safe_text(content),
                dxfattribs={
                    "layer": "PID_TEXT",
                    "char_height": char_height * scale,
                    "width": text["width"] * scale,
                },
            )
            entity.set_location(
                point(text["x"], text["y"]), rotation=-text.get("rotation", 0), attachment_point=1
            )
        else:
            # TEXT keeps short labels literal, including backslashes and braces.
            entity = model.add_text(
                content,
                dxfattribs={
                    "layer": "PID_TEXT",
                    "height": max(1, text["height"] * 0.8) * scale,
                    "rotation": -text.get("rotation", 0),
                },
            )
            entity.set_placement(
                point(text["x"], text["y"] + text["height"]), align=TextEntityAlignment.LEFT
            )
        set_identity(entity, source, generation, "text", text["id"])
    for line in scene["lines"]:
        layer = "PID_SIGNALS" if line.get("line_type") == "signal" else "PID_PIPES"
        entity = model.add_lwpolyline(
            [point(x, y) for x, y in line_points(line)],
            dxfattribs={"layer": layer, "flags": 128 if layer == "PID_SIGNALS" else 0},
        )
        set_identity(entity, source, generation, "line", line["id"])
    symbols = {str(item["id"]): item for item in scene["symbols"]}
    for edge in scene["topology_edges"]:
        # Inferred graph edges are reference geometry on a separate hidden layer.
        # They must not be mistaken for verified process piping.
        start, end = symbols[edge["source"]], symbols[edge["target"]]
        entity = model.add_line(
            point(start["x"] + start["width"] / 2, start["y"] + start["height"] / 2),
            point(end["x"] + end["width"] / 2, end["y"] + end["height"] / 2),
            dxfattribs={"layer": "PID_CONNECTIONS"},
        )
        set_identity(entity, source, generation, "connection", edge["id"])
    doc.layers.get("PID_CONNECTIONS").off()
    doc.set_modelspace_vport(
        height=source["height"] * scale * 1.12,
        center=(source["width"] * scale / 2, source["height"] * scale / 2),
    )
    stream = io.StringIO()
    doc.write(stream)
    return stream.getvalue().encode("utf-8")
