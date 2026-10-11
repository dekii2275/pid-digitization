"""Exercise real PDF upload, original download, annotations, filters and deletion."""

from __future__ import annotations

import argparse
import json
import uuid
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def sample_pdf() -> bytes:
    """Two vector pages of different sizes, generated without external packages."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 144 72] /Resources << >> /Contents 5 0 R >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 72 144] /Resources << >> /Contents 5 0 R >>",
    ]
    drawing = b"2 w 10 10 m 60 10 l 60 60 l 10 60 l S"
    objects.append(f"<< /Length {len(drawing)} >>\nstream\n".encode() + drawing + b"\nendstream")
    output = b"%PDF-1.4\n"
    offsets = [0]
    for index, value in enumerate(objects, start=1):
        offsets.append(len(output))
        output += f"{index} 0 obj\n".encode() + value + b"\nendobj\n"
    xref = len(output)
    output += f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode()
    output += b"".join(f"{offset:010d} 00000 n \n".encode() for offset in offsets[1:])
    output += (
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:18731")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    def request(path, method="GET", data=None, content_type=None):
        headers = {"Content-Type": content_type} if content_type else {}
        with urlopen(
            Request(base + path, method=method, data=data, headers=headers), timeout=60
        ) as response:
            return response.read()

    def json_request(path, **kwargs):
        return json.loads(request(path, **kwargs))

    source = sample_pdf()
    boundary = uuid.uuid4().hex
    name = f"data-smoke-{boundary[:8]}.pdf"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            "Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + source
        + f"\r\n--{boundary}--\r\n".encode()
    )
    document = json_request(
        "/api/v1/documents/upload",
        method="POST",
        data=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    url = f"/api/v1/documents/{document['id']}"
    try:
        assert document["page_count"] == 2
        assert document["file_path"].startswith("s3://")
        assert document["byte_size"] == len(source)
        assert request(document["original_url"]) == source
        assert not document["is_labeled"]
        second = json_request(url + "/pages/2")
        assert second["height"] > second["width"]
        assert request(second["preview_url"]).startswith(b"\xff\xd8")
        assert request(second["tile_url_template"].format(z=0, x=0, y=0)).startswith(b"\x89PNG")
        annotations_url = url + "/pages/2/annotations"
        saved = json_request(
            annotations_url,
            method="PUT",
            data=json.dumps(
                {
                    "revision": 0,
                    "symbols": [],
                    "texts": [
                        {
                            "id": "ocr-test",
                            "text": "P-101",
                            "x": 10,
                            "y": 10,
                            "width": 30,
                            "height": 20,
                        }
                    ],
                    "relations": [],
                }
            ).encode(),
            content_type="application/json",
        )
        assert saved["revision"] == 1
        labeled = json_request("/api/v1/documents?labeled=true")
        found = next(item for item in labeled if item["id"] == document["id"])
        assert found["labeled_pages"] == [2] and found["annotation_count"] == 1
        assert all(
            item["id"] != document["id"] for item in json_request("/api/v1/documents?labeled=false")
        )
        assert json_request(annotations_url)["texts"][0]["text"] == "P-101"
        assert request(annotations_url + "/export").startswith(b"PK")
    finally:
        json_request(url, method="DELETE")
    assert all(item["id"] != document["id"] for item in json_request("/api/v1/documents"))
    for path in (url, document["original_url"], annotations_url, second["preview_url"]):
        try:
            request(path)
        except HTTPError as error:
            assert error.code == 404
        else:
            raise AssertionError(f"Deleted drawing is still accessible: {path}")
    print(
        "PASS: PDF pages, MinIO original bytes, PostgreSQL annotations, labeled filter, export and deletion"
    )


if __name__ == "__main__":
    main()
