# -*- coding: utf-8 -*-
"""离线视觉后端基准工具。

样本目录结构：
    samples/<状态>/*.png

可选的同名 JSON 描述文件包含 value、resolution、dpi、region、allow_action。
没有描述文件时，文件名中的第一段数字会作为真实值；low_confidence 默认期望拒识。
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "outputs"))

from count_mode import VisionBackend, read_templates  # noqa: E402

try:
    from PIL import Image  # noqa: E402
except Exception:
    Image = None


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def _metadata(path):
    sidecar = path.with_suffix(".json")
    if sidecar.is_file():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8-sig"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    match = re.search(r"(?:^|[_-])([0-9]{1,6})(?:[_-]|$)", path.stem)
    if match:
        return {"value": int(match.group(1))}
    return {"value": None} if path.parent.name == "low_confidence" else {}


def load_samples(root):
    samples = []
    for path in sorted(Path(root).rglob("*")):
        if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
            continue
        metadata = _metadata(path)
        expected_set = "value" in metadata
        samples.append({
            "path": path,
            "state": path.parent.name,
            "expected": metadata.get("value"),
            "expected_set": expected_set,
            "resolution": metadata.get("resolution"),
            "dpi": metadata.get("dpi"),
            "region": metadata.get("region"),
            "allow_action": bool(metadata.get("allow_action", path.parent.name != "low_confidence")),
        })
    return samples


def _p(values, percentile):
    if not values:
        return 0.0
    values = sorted(values)
    index = min(len(values) - 1, max(0, int(round((percentile / 100) * (len(values) - 1)))))
    return round(float(values[index]), 3)


def _summary(rows, name, available=True, error=None):
    usable = [row for row in rows if row["expected_set"]]
    correct = sum(row["value"] == row["expected"] for row in usable)
    false_positive = sum(row["expected"] is None and row["value"] is not None for row in usable)
    reject = sum(row["expected"] is not None and row["value"] is None for row in usable)
    elapsed = [row["elapsed_ms"] for row in rows]
    return {
        "backend": name,
        "available": bool(available),
        "error": error,
        "samples": len(rows),
        "labeled_samples": len(usable),
        "accuracy": round(correct / len(usable), 4) if usable else None,
        "false_positive_count": false_positive,
        "reject_count": reject,
        "p50_ms": _p(elapsed, 50),
        "p95_ms": _p(elapsed, 95),
    }


def run_backend(samples, name, reader):
    rows = []
    for sample in samples:
        started = time.perf_counter()
        value = None
        error = None
        try:
            with Image.open(sample["path"]) as image:
                value = reader(image)
        except Exception as exc:
            error = str(exc)
        rows.append({
            "path": str(sample["path"]),
            "state": sample["state"],
            "expected": sample["expected"],
            "expected_set": sample["expected_set"],
            "value": value,
            "allow_action": sample["allow_action"],
            "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
            "error": error,
        })
    return rows


def benchmark(samples_dir, deadline_ms=850):
    if Image is None:
        raise RuntimeError("缺少 Pillow，无法读取样本")
    samples = load_samples(samples_dir)
    backend = VisionBackend(deadline_ms=deadline_ms)
    result_rows = {}
    result_rows["current"] = run_backend(
        samples,
        "current",
        lambda image: backend.read_image(image, deadline_ms=deadline_ms).value,
    )
    result_rows["opencv_template"] = run_backend(
        samples,
        "opencv_template",
        lambda image: read_templates(image)[0],
    )
    summaries = {
        name: _summary(rows, name)
        for name, rows in result_rows.items()
    }
    try:
        import maa  # noqa: F401
        summaries["maa"] = _summary([], "maa", available=True)
        summaries["maa"]["error"] = "未提供 MaaFramework 适配器；仅检测到 Python 模块"
    except Exception as exc:
        summaries["maa"] = _summary([], "maa", available=False, error="MaaFramework 不可用：%s" % exc)
    records = []
    all_paths = sorted({row["path"] for rows in result_rows.values() for row in rows})
    for path in all_paths:
        record = {"path": path}
        for name, rows in result_rows.items():
            row = next(item for item in rows if item["path"] == path)
            record[name] = {
                "state": row["state"],
                "expected": row["expected"],
                "value": row["value"],
                "allow_action": row["allow_action"],
                "elapsed_ms": row["elapsed_ms"],
                "error": row["error"],
            }
        records.append(record)
    return {
        "samples_dir": str(Path(samples_dir).resolve()),
        "deadline_ms": deadline_ms,
        "summaries": summaries,
        "records": records,
    }


def write_outputs(result, json_path, csv_path):
    if json_path:
        Path(json_path).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if csv_path:
        with Path(csv_path).open("w", encoding="utf-8-sig", newline="") as output:
            writer = csv.writer(output)
            writer.writerow(["path", "backend", "state", "expected", "value", "allow_action", "elapsed_ms", "error"])
            for record in result["records"]:
                for name, row in record.items():
                    if name == "path":
                        continue
                    writer.writerow([record["path"], name, row["state"], row["expected"], row["value"],
                                     row["allow_action"], row["elapsed_ms"], row["error"] or ""])


def main(argv=None):
    parser = argparse.ArgumentParser(description="比较本地视觉后端，不执行任何输入动作")
    parser.add_argument("samples_dir", help="按状态分类的脱敏样本目录")
    parser.add_argument("--deadline-ms", type=int, default=850)
    parser.add_argument("--json", dest="json_path", default="vision-benchmark.json")
    parser.add_argument("--csv", dest="csv_path", default="vision-benchmark.csv")
    args = parser.parse_args(argv)
    result = benchmark(args.samples_dir, deadline_ms=max(100, min(1000, args.deadline_ms)))
    write_outputs(result, args.json_path, args.csv_path)
    print(json.dumps(result["summaries"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
