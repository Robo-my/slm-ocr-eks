# Layout-detection eval (PP-DocLayoutV3)

Measures what the **layout stage** of the pipeline hands to the transcriber, before any GPU or vLLM is involved. It runs the same detector the worker uses — PP-DocLayoutV3 via the GLM-OCR SDK — on CPU, over any PDF or folder of images.

## Run it

```bash
uv venv .venv --python 3.12
uv pip install --python .venv/bin/python -r eval/layout-detection/requirements.txt

# batch 1 + a memory cap: one 150-DPI page peaks at ~1.9 GB RSS on CPU
OMP_NUM_THREADS=4 systemd-run --user --scope -q -p MemoryMax=2500M -p MemorySwapMax=0 \
  .venv/bin/python -I eval/layout-detection/run_layout.py path/to/document.pdf
```

Options: `--pages 1-5`, `--dpi 150`, `--threshold 0.3`, `--batch-size 1`, `--device cpu|cuda`, `--remove-rules`, `--ink-fallback`, `--no-vis`.

`--remove-rules` erases long horizontal/vertical lines (ruled paper, margins) before detection. On ruled answer sheets the raw detector labels the whole grid as one "table" or "chart"; with the lines erased it finds the handwriting instead.

`--ink-fallback` adds every blob of unread writing (see *ink recall* below) as an extra `ink` text region, so the token numbers include the cost of recovering what the detector missed. Without it, the blobs are only drawn and listed.

Outputs land in `eval/layout-detection/runs/<name>/` (gitignored — inputs are often real documents):

| File | Contents |
| :--- | :--- |
| `summary.json` | aggregate + per-page metrics |
| `regions.jsonl` | one line per page: every region's label, score, reading-order index, bbox, polygon; `missed_ink` lists the unread-writing blobs |
| `vis/page_NN.jpg` | side-by-side overlay: axis-aligned bboxes (left) vs polygons (right); red `ink` boxes are unread writing |

## What happens to each label

| Group | Labels | Pipeline action |
| :--- | :--- | :--- |
| transcribe | text, paragraph_title, doc_title, abstract, content, algorithm, figure_title, reference_content, vision_footnote, table, formula, formula_number | cropped and sent to the VLM |
| passthrough | image, chart, seal | kept as an image, not transcribed |
| drop | header, footer, number, footnote, aside_text, reference | page furniture, discarded |

## Metrics

- **sent area** — fraction of the page covered by transcribe-group boxes. One-stage OCR always sends 100%.
- **visual tokens** — rough estimate at 28×28 px per token (Qwen-VL-style: 14 px patches, 2×2 merge). One-stage = whole page; two-stage = sum of transcribe-group crops at the same resolution. Real processors also resize to min/max pixel budgets, so treat this as a ratio, not an absolute count.
- **bbox excess** — mean share of each transcribe region's bounding box that lies outside its polygon (area a rectangle crop reads that the polygon would not).
- **overlap** — share of sent area covered by two or more transcribe crops (content that would be read twice), for bboxes and for polygons.
- **ink recall** — how much of the writing on the page lands inside a transcribe crop. This is a label-free stand-in for detector recall:
  1. *Ink* = pixels darker than grey 160 on the page with ruled lines erased (always, even when detection ran on the raw page). A 5% border band, where scanner edge shadow and registration marks sit, and specks under 10 px are ignored.
  2. Each ink pixel counts once, in the first group whose bboxes contain it: transcribe → passthrough → drop → none (`ink_read_frac`, `ink_passthrough_frac`, `ink_drop_frac`, `ink_missed_frac`).
  3. *Unread* ink is ink outside every transcribe and drop box, which includes handwriting swallowed by an "image"/"chart" box. Unread strokes are dilated into word/line blobs. A blob counts as writing if it holds ≥ 0.005% of the page area in ink and fills ≥ 3% of its own box; the density floor rejects diagonal strike-through lines.
  4. `ink_recall` = read ink / (read ink + unread writing). Dropped furniture and stray specks don't count against it. The summary pools pixels across pages, and `pages_below_recall_flag` lists pages under 0.95.
  5. `fallback_tokens` = visual tokens for cropping every unread-writing blob — the price of the fallback.
- **latency** — ms per page on the chosen device, after a warm-up page.

## Results

See [`docs/journal/week-02.md`](../../docs/journal/week-02.md#layout-stage-results-32-page-handwritten-exam-scan-cpu).
