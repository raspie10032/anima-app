"""Explicit download of only the original cache model's vision weights.

HTTP ranges avoid fetching the 10 GB language model. No credentials, remote
Python code, or implicit downloads are used. The extracted tensors are unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import urllib.request
from .import_snapshot import file_digest

MODEL = "p-e-w/gemma-4-E2B-it-heretic-ara"
REVISION = "c9a1d4c031981f14d86eeb0c7d87de7fafd34513"
PROCESSOR = "unsloth/gemma-4-e2b-it"


def get_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def read_range(url, start, end):
    # Distinct query strings prevent a cached range from serving the wrong bytes.
    request = urllib.request.Request(f"{url}?rs_range={start}-{end}",
                                     headers={"Range": f"bytes={start}-{end}"})
    with urllib.request.urlopen(request, timeout=90) as response:
        expected = f"bytes {start}-{end}/"
        if response.status != 206 or not response.headers.get("Content-Range", "").startswith(expected):
            raise RuntimeError("Server did not honor the requested byte range")
        result = response.read(end - start + 2)
    if len(result) != end - start + 1:
        raise RuntimeError("Truncated or oversized range")
    return result


def prepare(output, progress=lambda done, total: None, cancelled=lambda: False):
    expected = json.loads(Path(__file__).with_name('model.json').read_text(encoding='utf-8'))
    output.mkdir(parents=True, exist_ok=False)
    base = f"https://huggingface.co/{MODEL}/resolve/{REVISION}"
    config = get_json(f"{base}/config.json")["vision_config"]
    config["architectures"] = ["Gemma4VisionModel"]
    processor_rev = expected['processor_revision']
    processor = get_json(f"https://huggingface.co/{PROCESSOR}/resolve/{processor_rev}/processor_config.json")
    url = f"{base}/model.safetensors"
    size = struct.unpack("<Q", read_range(url, 0, 7))[0]
    if size > 8 * 1024**2:
        raise ValueError("Unexpected safetensors header size")
    header = json.loads(read_range(url, 8, size + 7))
    if hashlib.sha256(json.dumps(header, sort_keys=True).encode()).hexdigest() != expected['source_header_sha256']:
        raise ValueError('PROVENANCE_MISMATCH: vision source header changed')
    prefix = "model.vision_tower."
    selected = sorted(((k, v) for k, v in header.items() if k.startswith(prefix)),
                      key=lambda item: item[1]["data_offsets"][0])
    if not selected:
        raise ValueError("No vision tower tensors")
    start = selected[0][1]["data_offsets"][0]
    end = selected[-1][1]["data_offsets"][1]
    if len(selected) != expected['tensor_count'] or end-start != expected['tensor_bytes']:
        raise ValueError('PROVENANCE_MISMATCH: vision tensor layout changed')
    cursor = start
    extracted = {}
    for key, entry in selected:
        lo, hi = entry["data_offsets"]
        if lo != cursor:
            raise ValueError("Vision tensors are not contiguous")
        extracted[key.removeprefix(prefix)] = {**entry, "data_offsets": [lo - start, hi - start]}
        cursor = hi
    packed = json.dumps(extracted, separators=(",", ":")).encode()
    packed += b" " * (-len(packed) % 8)
    target = output / "model.safetensors"
    tmp = target.with_suffix(".part")
    with tmp.open("xb") as stream:
        stream.write(struct.pack("<Q", len(packed)))
        stream.write(packed)
        chunk = 16 * 1024**2
        for offset in range(start, end, chunk):
            if cancelled():
                raise InterruptedError('cancelled')
            block_end = min(offset + chunk, end)
            stream.write(read_range(url, size + 8 + offset, size + 8 + block_end - 1))
            progress(block_end-start, end-start)
    tmp.rename(target)
    (output / "config.json").write_bytes((json.dumps(config, indent=2) + "\n").encode())
    (output / "preprocessor_config.json").write_bytes((json.dumps(processor["image_processor"], indent=2) + "\n").encode())
    hashes = {}
    for file in output.iterdir():
        hashes[file.name] = file_digest(file)
    if hashes != expected['files']:
        raise ValueError('PROVENANCE_MISMATCH: downloaded files do not match pinned hashes')
    receipt = {"model": MODEL, "model_revision": REVISION, "processor": PROCESSOR,
               "processor_revision": processor_rev, "tensor_count": len(selected),
               "tensor_bytes": end - start, "source_header_sha256": hashlib.sha256(
                   json.dumps(header, sort_keys=True).encode()).hexdigest(), "files": hashes,
               "note": "Unchanged vision tensors only. Legacy cache compatibility requires separate measurement."}
    (output / "provenance.json").write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    prepare(parser.parse_args().output)
