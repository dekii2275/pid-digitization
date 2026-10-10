"""Check deployed UI, proxy, catalog, uploads and optional real AI pipeline.

Only the standard library is required. Uses a bundled symbol preview as input.
"""

from __future__ import annotations

import argparse
import json
import time
import uuid
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://localhost:18731")
    parser.add_argument("--pipeline", action="store_true")
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    def request(path: str, *, data=None, content_type=None):
        headers = {"Content-Type": content_type} if content_type else {}
        with urlopen(Request(base + path, data=data, headers=headers), timeout=30) as response:
            return response.status, response.headers.get_content_type(), response.read()

    def json_request(path: str, **kwargs):
        return json.loads(request(path, **kwargs)[2])

    status, mime, body = request("/")
    assert status == 200 and mime == "text/html" and b'id="root"' in body, "UI failed"
    symbols = json_request("/api/v1/symbol-library")
    assert isinstance(symbols, list) and symbols, "Fresh database did not seed its symbol catalog"
    for symbol in symbols:
        assert request(symbol["preview"])[1].startswith("image/"), "Symbol preview failed"
        assert request(symbol["source_url"])[2], "Symbol source is empty"

    boundary = uuid.uuid4().hex
    image = (ROOT / "src/app/seed_symbols/PNG.png").read_bytes()
    upload = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="smoke.png"\r\n'
        'Content-Type: image/png\r\n\r\n'
    ).encode() + image + f"\r\n--{boundary}--\r\n".encode()
    drawing = json_request("/api/v1/documents/upload", data=upload, content_type=f"multipart/form-data; boundary={boundary}")
    assert drawing["width"] > 0 and drawing["height"] > 0
    assert request(drawing["preview_url"])[1] == "image/jpeg"
    assert request(drawing["tile_url_template"].format(z=0, x=0, y=0))[1] == "image/png"
    print("PASS: UI, Nginx proxy, PostgreSQL seed/files, upload, preview and tile", flush=True)

    if args.pipeline:
        job = json_request(f"/api/v1/documents/{drawing['id']}/run-all", data=b"")
        deadline = time.monotonic() + args.timeout
        last_stage = None
        while job["status"] not in {"FAILED", "COMPLETED"}:
            if time.monotonic() > deadline:
                raise TimeoutError(f"Pipeline timed out: {job}")
            if job["stage"] != last_stage:
                print(f"Pipeline: {job['stage']} ({job['progress']}%)", flush=True)
                last_stage = job["stage"]
            time.sleep(2)
            job = json_request(f"/api/v1/jobs/{job['job_id']}")
        assert job["status"] == "COMPLETED", json.dumps(job, ensure_ascii=False)
        scene = json_request(job["results_url"])
        assert isinstance(scene, dict) and all(isinstance(scene.get(name), list) for name in ("symbols", "texts", "lines", "topology_edges")), "Editor scene missing"
        saved = json_request(f"/api/v1/jobs/{job['job_id']}/final-results", data=json.dumps(scene).encode(), content_type="application/json")
        assert saved["result"]["review"]["status"] == "FINAL"
        assert json_request(f"/api/v1/jobs/{job['job_id']}/final-results")["review"]["status"] == "FINAL"
        print("PASS: real YOLO -> PaddleOCR -> lines -> topology -> editor scene", flush=True)


if __name__ == "__main__":
    main()
