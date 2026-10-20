"""Run PP-DocLayoutV3 (via the GLM-OCR SDK) over a PDF or image folder and measure
what the layout stage would hand to the transcriber.

Per page it records every detected region (label, score, reading order, bbox, polygon)
and computes:
  - how much of the page the transcriber actually receives (vs the whole page in one-stage OCR)
  - a visual-token estimate for one-stage vs two-stage
  - how much extra area an axis-aligned bbox crop takes compared with the polygon
  - how much transcribed crops overlap each other (content read twice)
  - how much of the page's ink lands in a transcribed region, and where the rest goes
  - layout latency on the current device

Outputs go to runs/<input-name>/ (gitignored: inputs may be real documents).
"""

import argparse
import json
import math
import statistics
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pymupdf
import torch
from PIL import Image, ImageDraw, ImageFont

from glmocr.config import LayoutConfig
from glmocr.layout.layout_detector import PPDocLayoutDetector

MODEL_ID = "PaddlePaddle/PP-DocLayoutV3_safetensors"

# What the pipeline does with each detected label.
# transcribe: cropped and sent to the VLM. passthrough: kept as an image. drop: page furniture.
LABEL_GROUPS = {
    "transcribe": [
        "abstract", "algorithm", "content", "doc_title", "figure_title", "formula",
        "formula_number", "paragraph_title", "reference_content", "table", "text",
        "vision_footnote",
    ],
    "passthrough": ["chart", "image", "seal"],
    "drop": ["aside_text", "footer", "footnote", "header", "number", "reference"],
}

# Qwen-VL-style vision encoders emit one token per 28x28 px (14 px patches, 2x2 merge).
PX_PER_TOKEN = 28
GRID = 1000  # the SDK returns coordinates normalised to 0..1000

INK_LEVEL = 160  # grey level below which a pixel counts as ink
BORDER_FRAC = 0.05  # scanner edge shadow and registration marks live in this band around the page
MIN_SPECK_PX = 10  # connected ink smaller than this is scanner noise
JOIN_FRAC = (0.03, 0.01)  # gap (page width, height) bridged when joining strokes into word/line blobs
# A blob of ink outside every region becomes a fallback crop only if it holds enough ink
# (fraction of page area) and fills enough of its own box -- a diagonal strike-through doesn't.
MIN_BLOB_FRAC = 5e-5
MIN_BLOB_DENSITY = 0.03
RECALL_FLAG = 0.95  # flag a page whose ink recall is below this

COLORS = {
    "text": (40, 110, 220), "table": (20, 160, 80), "formula": (150, 60, 200),
    "passthrough": (240, 140, 20), "drop": (130, 130, 130),
    "ink": (220, 30, 30), "missed": (220, 30, 30),
}


def iter_pages(src: Path, dpi: int, pages: str | None):
    """Yield (name, image) one page at a time, so memory stays flat on long PDFs."""
    if src.suffix.lower() == ".pdf":
        doc = pymupdf.open(src)
        names = [f"page_{i + 1:02d}" for i in range(doc.page_count)]
    elif src.is_dir():
        files = sorted(p for p in src.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".tif", ".tiff"})
        names = [p.stem for p in files]
    else:
        files, names = [src], [src.stem]

    keep = range(len(names))
    if pages:
        lo, _, hi = pages.partition("-")
        keep = range(int(lo) - 1, min(int(hi or lo), len(names)))

    for i in keep:
        if src.suffix.lower() == ".pdf":
            pix = doc[i].get_pixmap(dpi=dpi)
            yield names[i], Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        else:
            yield names[i], Image.open(files[i]).convert("RGB")


def ink_mask(img: Image.Image) -> np.ndarray:
    return (cv2.cvtColor(np.array(img), cv2.COLOR_RGB2GRAY) < INK_LEVEL).astype(np.uint8) * 255


def remove_rules(img: Image.Image) -> Image.Image:
    """Erase long horizontal/vertical lines (ruled paper, margins, table grids), keep strokes."""
    arr = np.array(img)
    ink = ink_mask(img)
    h = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (img.width // 8, 1)))
    v = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, img.height // 8)))
    lines = cv2.dilate(h | v, np.ones((3, 3), np.uint8))
    arr[lines > 0] = 255
    return Image.fromarray(arr)


def chunks(it, n):
    batch = []
    for item in it:
        batch.append(item)
        if len(batch) == n:
            yield batch
            batch = []
    if batch:
        yield batch


def group_of(label: str) -> str:
    for group, labels in LABEL_GROUPS.items():
        if label in labels:
            return group
    return "transcribe"  # unknown labels are safer read than dropped


def color_of(region: dict) -> tuple[int, int, int]:
    if region["group"] != "transcribe":
        return COLORS[region["group"]]
    return COLORS.get(region["label"], COLORS["text"])


def shoelace(points: list[list[int]]) -> float:
    if len(points) < 3:
        return 0.0
    xs, ys = zip(*points)
    return 0.5 * abs(sum(xs[i] * ys[i - 1] - xs[i - 1] * ys[i] for i in range(len(points))))


def raster(shape: str, region: dict) -> np.ndarray:
    mask = Image.new("1", (GRID, GRID), 0)
    draw = ImageDraw.Draw(mask)
    if shape == "bbox":
        draw.rectangle(region["bbox_2d"], fill=1)
    else:
        draw.polygon([tuple(p) for p in region["polygon"]], fill=1)
    return np.array(mask, dtype=np.uint8)


def crop_tokens(region: dict, width: int, height: int) -> int:
    x1, y1, x2, y2 = region["bbox_2d"]
    w_px, h_px = (x2 - x1) * width / GRID, (y2 - y1) * height / GRID
    return math.ceil(w_px / PX_PER_TOKEN) * math.ceil(h_px / PX_PER_TOKEN)


def page_metrics(regions: list[dict], width: int, height: int) -> dict:
    sent = [r for r in regions if r["group"] == "transcribe"]
    one_stage_tokens = math.ceil(width / PX_PER_TOKEN) * math.ceil(height / PX_PER_TOKEN)
    two_stage_tokens = sum(crop_tokens(r, width, height) for r in sent)

    m = {
        "regions": len(regions),
        "by_group": dict(Counter(r["group"] for r in regions)),
        "by_label": dict(Counter(r["label"] for r in regions)),
        "one_stage_tokens": one_stage_tokens,
        "two_stage_tokens": two_stage_tokens,
        "sent_area_frac": 0.0,
        "bbox_excess_frac": None,
        "bbox_overlap_frac": 0.0,
        "poly_overlap_frac": 0.0,
    }
    if not sent:
        return m

    bbox_cover = sum(raster("bbox", r) for r in sent)
    poly_cover = sum(raster("poly", r) for r in sent)
    m["sent_area_frac"] = float((bbox_cover > 0).mean())
    m["bbox_overlap_frac"] = float((bbox_cover > 1).sum() / max((bbox_cover > 0).sum(), 1))
    m["poly_overlap_frac"] = float((poly_cover > 1).sum() / max((poly_cover > 0).sum(), 1))

    excess = []
    for r in sent:
        x1, y1, x2, y2 = r["bbox_2d"]
        box_area = (x2 - x1) * (y2 - y1)
        if box_area > 0 and len(r["polygon"]) >= 3:
            excess.append(1 - min(shoelace(r["polygon"]) / box_area, 1.0))
    m["bbox_excess_frac"] = statistics.mean(excess) if excess else None
    return m


def ink_coverage(img: Image.Image, regions: list[dict]) -> tuple[dict, list[dict]]:
    """Where the page's ink ends up (read / passthrough / drop / missed), plus boxes around unread writing.

    ink_recall = ink inside transcribe crops / (that + unread ink that looks like writing). Unread means
    outside every transcribe and drop region -- so handwriting swallowed by an "image"/"chart" box counts
    as unread, while dropped furniture (headers, footers) and stray specks don't count against recall.
    """
    ink = ink_mask(remove_rules(img)) > 0  # ruled lines are paper, not content
    h, w = ink.shape
    bx, by = int(w * BORDER_FRAC), int(h * BORDER_FRAC)
    ink[:by], ink[h - by:], ink[:, :bx], ink[:, w - bx:] = False, False, False, False
    n, comp, stats, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), connectivity=8)
    keep = stats[:, cv2.CC_STAT_AREA] >= MIN_SPECK_PX
    keep[0] = False
    ink = keep[comp]

    # Each ink pixel counts once, in the first group whose bboxes contain it.
    covers, claimed = {}, np.zeros_like(ink)
    for group in ("transcribe", "passthrough", "drop"):
        cover = np.zeros_like(ink)
        for r in regions:
            if r["group"] == group:
                x1, y1, x2, y2 = r["bbox_2d"]
                cover[y1 * h // GRID:y2 * h // GRID, x1 * w // GRID:x2 * w // GRID] = True
        covers[group] = cover & ~claimed
        claimed |= cover
    px = {g: int((ink & c).sum()) for g, c in covers.items()}
    unread = (ink & ~(covers["transcribe"] | covers["drop"])).astype(np.uint8)

    # Join unread strokes into word/line blobs and box the ones that look like writing.
    kernel = (max(int(w * JOIN_FRAC[0]), 1), max(int(h * JOIN_FRAC[1]), 1))
    joined = cv2.dilate(unread, cv2.getStructuringElement(cv2.MORPH_RECT, kernel))
    n, comp, stats, _ = cv2.connectedComponentsWithStats(joined, connectivity=8)
    blobs, writing_px = [], 0
    for i in range(1, n):
        x, y, bw, bh, _ = stats[i]
        blob_ink = int(unread[y:y + bh, x:x + bw][comp[y:y + bh, x:x + bw] == i].sum())
        if blob_ink < MIN_BLOB_FRAC * w * h or blob_ink / (bw * bh) < MIN_BLOB_DENSITY:
            continue
        writing_px += blob_ink
        x1, y1 = max(x - w // 100, 0), max(y - h // 100, 0)
        x2, y2 = min(x + bw + w // 100, w), min(y + bh + h // 100, h)
        box = [round(x1 * GRID / w), round(y1 * GRID / h), round(x2 * GRID / w), round(y2 * GRID / h)]
        blobs.append({
            "index": len(regions) + len(blobs), "label": "ink", "score": 0.0, "group": "missed",
            "bbox_2d": box, "polygon": [[box[0], box[1]], [box[2], box[1]], [box[2], box[3]], [box[0], box[3]]],
        })
    total = int(ink.sum())

    def share(v):
        return round(v / total, 3) if total else None

    read = px["transcribe"]
    return {
        "ink_px": total,
        "ink_read_frac": share(read),
        "ink_passthrough_frac": share(px["passthrough"]),
        "ink_drop_frac": share(px["drop"]),
        "ink_missed_frac": share(int((ink & ~claimed).sum())),
        "writing_unread_px": writing_px,
        "ink_recall": round(read / (read + writing_px), 3) if read + writing_px else None,
        "missed_blobs": len(blobs),
        "fallback_tokens": sum(crop_tokens(b, w, h) for b in blobs),
    }, blobs


def visualise(img: Image.Image, regions: list[dict], path: Path, height: int = 1100):
    scale = height / img.height
    base = img.resize((int(img.width * scale), height))
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 13)
    panels = []
    for shape in ("bbox", "polygon"):
        panel = base.copy().convert("RGBA")
        overlay = Image.new("RGBA", panel.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        sx, sy = panel.width / GRID, panel.height / GRID
        for r in regions:
            c = color_of(r)
            if shape == "bbox":
                x1, y1, x2, y2 = r["bbox_2d"]
                draw.rectangle([x1 * sx, y1 * sy, x2 * sx, y2 * sy], fill=c + (40,), outline=c + (255,), width=2)
            else:
                pts = [(x * sx, y * sy) for x, y in r["polygon"]]
                draw.polygon(pts, fill=c + (40,), outline=c + (255,), width=2)
            x1, y1 = r["bbox_2d"][0] * sx, r["bbox_2d"][1] * sy
            tag = f"{r['index']} {r['label']} {r['score']:.2f}"
            draw.rectangle([x1, y1 - 16, x1 + draw.textlength(tag, font=font) + 6, y1], fill=c + (220,))
            draw.text((x1 + 3, y1 - 15), tag, font=font, fill=(255, 255, 255, 255))
        panel = Image.alpha_composite(panel, overlay).convert("RGB")
        ImageDraw.Draw(panel).text((10, 10), shape, font=ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22), fill=(200, 0, 0))
        panels.append(panel)
    out = Image.new("RGB", (panels[0].width * 2 + 10, height), "white")
    out.paste(panels[0], (0, 0))
    out.paste(panels[1], (panels[0].width + 10, 0))
    out.save(path, quality=85)


def main():
    ap = argparse.ArgumentParser(description="PP-DocLayoutV3 layout-stage eval")
    ap.add_argument("input", type=Path, help="PDF, image, or folder of images")
    ap.add_argument("--pages", help="page range, e.g. 1-5")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--threshold", type=float, default=0.3)
    # One 150-DPI page peaks at ~1.9 GB RSS on CPU; each extra page in a batch adds roughly that again.
    ap.add_argument("--batch-size", type=int, default=1)
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--remove-rules", action="store_true", help="erase ruled lines before detection")
    ap.add_argument("--ink-fallback", action="store_true", help="send ink missed by every region as extra text crops")
    ap.add_argument("--no-vis", action="store_true")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()

    out = args.out or Path(__file__).parent / "runs" / args.input.stem
    (out / "vis").mkdir(parents=True, exist_ok=True)

    cfg = LayoutConfig(
        model_dir=MODEL_ID,
        device=args.device,
        threshold=args.threshold,
        batch_size=args.batch_size,
        label_task_mapping=LABEL_GROUPS,
        id2label=None,  # read by the detector but not declared on LayoutConfig; None = use the model's labels
    )
    detector = PPDocLayoutDetector(cfg)
    t0 = time.perf_counter()
    detector.start()
    load_s = time.perf_counter() - t0

    pages = iter_pages(args.input, args.dpi, args.pages)
    if args.remove_rules:
        pages = ((name, remove_rules(img)) for name, img in pages)

    _, first = next(iter_pages(args.input, args.dpi, args.pages))
    detector.process([first])  # warm-up
    del first

    per_page, page_ms = [], []
    with open(out / "regions.jsonl", "w") as f:
        for batch in chunks(pages, args.batch_size):
            t0 = time.perf_counter()
            results = detector.process([img for _, img in batch])
            page_ms.append((time.perf_counter() - t0) * 1000 / len(batch))

            for (name, img), regions in zip(batch, results):
                for r in regions:
                    r["group"] = r.pop("task_type")
                ink, blobs = ink_coverage(img, regions)  # always measured against the detector's own regions
                if args.ink_fallback:
                    for b in blobs:
                        b["group"] = "transcribe"
                    regions, blobs = regions + blobs, []
                m = page_metrics(regions, *img.size)
                per_page.append({"page": name, "size": list(img.size), **m, **ink})
                f.write(json.dumps({"page": name, "size": list(img.size), "regions": regions, "missed_ink": blobs}) + "\n")
                if not args.no_vis:
                    visualise(img, regions + blobs, out / "vis" / f"{name}.jpg")
            print(f"  {batch[-1][0]}: {page_ms[-1]:.0f} ms/page", flush=True)

    def total(key):
        return sum(p[key] for p in per_page)

    # Ink metrics are pooled over pixels, so a near-empty page barely counts.
    inked = [p for p in per_page if p["ink_px"]]
    ink_total = max(sum(p["ink_px"] for p in inked), 1)
    read_px = sum(p["ink_read_frac"] * p["ink_px"] for p in inked)
    writing_px = read_px + total("writing_unread_px")

    def ink_share(key):
        return round(sum(p[key] * p["ink_px"] for p in inked) / ink_total, 3)

    sent = [p["sent_area_frac"] for p in per_page]
    excess = [p["bbox_excess_frac"] for p in per_page if p["bbox_excess_frac"] is not None]
    summary = {
        "input": args.input.name,
        "pages": len(per_page),
        "dpi": args.dpi,
        "threshold": args.threshold,
        "device": args.device,
        "remove_rules": args.remove_rules,
        "ink_fallback": args.ink_fallback,
        "torch_threads": torch.get_num_threads(),
        "model_load_s": round(load_s, 2),
        "batch_size": args.batch_size,
        "latency_ms_per_page_median": round(statistics.median(page_ms), 1),
        "latency_ms_per_page_max": round(max(page_ms), 1),
        "regions_total": total("regions"),
        "regions_per_page_mean": round(total("regions") / len(per_page), 1),
        "labels": dict(sum((Counter(p["by_label"]) for p in per_page), Counter()).most_common()),
        "groups": dict(sum((Counter(p["by_group"]) for p in per_page), Counter())),
        "one_stage_tokens": total("one_stage_tokens"),
        "two_stage_tokens": total("two_stage_tokens"),
        "sent_area_frac_mean": round(statistics.mean(sent), 3),
        "bbox_excess_frac_mean": round(statistics.mean(excess), 3) if excess else None,
        "bbox_overlap_frac_mean": round(statistics.mean(p["bbox_overlap_frac"] for p in per_page), 3),
        "poly_overlap_frac_mean": round(statistics.mean(p["poly_overlap_frac"] for p in per_page), 3),
        "ink_recall": round(read_px / writing_px, 3) if writing_px else None,
        "ink_read_frac": ink_share("ink_read_frac"),
        "ink_passthrough_frac": ink_share("ink_passthrough_frac"),
        "ink_drop_frac": ink_share("ink_drop_frac"),
        "ink_missed_frac": ink_share("ink_missed_frac"),
        "pages_below_recall_flag": [
            p["page"] for p in per_page if p["ink_recall"] is not None and p["ink_recall"] < RECALL_FLAG
        ],
        "missed_blobs": total("missed_blobs"),
        "fallback_tokens": total("fallback_tokens"),
        "per_page": per_page,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    print(json.dumps({k: v for k, v in summary.items() if k != "per_page"}, indent=2))
    print(f"\nwrote {out}/summary.json, regions.jsonl" + ("" if args.no_vis else ", vis/*.jpg"))


if __name__ == "__main__":
    main()
