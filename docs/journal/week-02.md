# Week 2 — SOTA OCR & Visual Document Understanding

**Focus:** why this pipeline is two-stage (layout detector → VLM transcriber) rather than one big page-level VLM, and a first hands-on look at the layout stage on real scans. No cloud infrastructure this week — the cluster stays destroyed, $0 spend.

## What I built

- [`eval/layout-detection/`](../../eval/layout-detection/): a CPU harness that runs PP-DocLayoutV3 through the GLM-OCR SDK (the same detector the Week 5 worker will run) over any PDF or image folder, and measures what the layout stage would hand to the transcriber: page area actually sent, visual-token estimate for one-stage vs two-stage, bbox-vs-polygon crop waste, crop overlap, latency, and **ink recall** — how much of the writing on the page actually lands in a transcribed crop.
- Ran it on a real 32-page scanned exam answer booklet (handwritten maths, ruled lines, marks table, rotated margin text, QR codes). Found that ruled paper breaks the detector, added a `--remove-rules` pre-processing option, and re-measured. Then replaced by-eye judging with the ink-recall check, which also boxes the writing the detector missed (`--ink-fallback` sends those boxes as extra crops). Results below; the document itself stays out of the repo.

## Key lessons worth remembering

1. **OCR is speech-to-text for images.** The layout detector plays the role of a voice-activity detector: find the regions worth reading, throw away the silence (whitespace, margins). The transcriber is the generative model that does the actual reading.
2. **CTC is how early OCR learned alignment without boxes.** CRNN (CNN features → BiLSTM) emits one label per thin vertical slice plus a *blank*. Decoding merges repeats then drops blanks — the blank is what lets `l ε l` survive as a real double letter. Training sums the probability of every slice sequence that collapses to the target, so nobody has to annotate character boxes.
3. **Transformers moved the hard work into the transcriber.** ViT tiles the image into 16×16 patches; TrOCR replaced CNN+LSTM with a ViT encoder + text decoder but still needed a line detector; Donut (Swin encoder + BART-style decoder) dropped detection entirely and read the whole page. The detector no longer has to isolate characters — just regions.
4. **Today there are three families:** teacher→student distillation (huge offline model trains a small production model), one-stage page VLMs (whole page → Markdown), and hybrid layout-first pipelines (fast layout parser → specialised transcriber per region). This repo is the hybrid.
5. **One-stage pays for whitespace, quadratically.** A page becomes ~5–7k visual tokens before a single word is generated, and prefill attention cost grows with the square of that. Compression encoders (~6k → ~1k tokens per page) cut per-request KV-cache from ~12 GB to ~2 GB and move the bottleneck from prefill compute to decode bandwidth.
6. **The real win of two-stage is systems engineering, not accuracy.** Sending one page at a time leaves tensor cores idle during decode (memory-bound, <15% utilisation). Many small crops from many pages fed into continuous batching (vLLM) keep decode slots full — same GPU, several times the pages per hour.
7. **Rectangles fail on real scans; polygons fix it.** An axis-aligned box around a tilted block grows into the neighbouring column, and the transcriber faithfully reads both. PP-DocLayoutV3 outputs polygons and a reading order, is encoder-only (~33M params), and needs no decoding loop.
8. **Character error rate is the wrong metric for production.** A table with every character right but two columns swapped is still a wrong document. Judge on structure, reading order, formula correctness, figure description, and cost per page.
9. **Two-stage vs one-stage is a workload decision.** Two-stage for varied, messy, precision-critical batch work and selective extraction (e.g. tables only from a 200-page PDF). One-stage for clean, short, latency-sensitive input such as a synchronous single-image API.

## Layout-stage results (32-page handwritten exam scan, CPU)

**Input:** a real 32-page scanned maths exam answer booklet (A4, office scanner, rendered at 150 DPI): 1 printed cover form, 14 handwritten answer pages on ruled paper, 14 unused ruled pages struck through with a diagonal line, 3 blank/cover pages. CPU, 4 threads, batch 1, threshold 0.3. Region quality first judged by eye on the overlays, then measured with ink recall.

| Page type | Raw scan | Ruled lines erased first (`--remove-rules`) |
| :--- | :--- | :--- |
| Printed cover form (1) | ✅ 23 regions, all correct: title, form fields, instructions, marks table (0.97, handwritten marks inside), header/footer | ✅ unchanged — table still found, same 16 transcribe regions |
| Handwritten answers (14) | ❌ 8 → one whole-page **"table"** crop · 4 → whole-page **"chart"** (passthrough: handwriting never transcribed) · 2 → fine-grained formulas, final answers missed | ⚠️ tight text/formula regions instead of whole-page crops — but lines missed on most pages (ink recall 0.72, below) |
| Blank struck-out ruled pages (14) | ❌ 8 → whole-page "table" **sent for transcription** · 3 → "chart" · 3 skipped | ✅ nothing transcribed; strike lines become "image" (passthrough) |

Visual-token estimate (28 px/token):

| Pages | One-stage | Two-stage, raw | Lines erased | Lines erased + ink fallback |
| :--- | ---: | ---: | ---: | ---: |
| Handwritten 3–16 | 39,690 | 20,294 (51%) | 3,118 (8%) | 4,808 (12%) |
| Blank struck 17–30 | 39,690 | 21,385 (54%) | 53 (0.1%) | 73 (0.2%) |
| **Ink recall, handwritten 3–16** | 1.00 | 0.79 (via whole-page crops) | **0.72** | all flagged writing cropped |

Latency: **~2.5 s/page median** on laptop CPU (3.3 s max), model load 2 s, **peak RSS 1.87 GB at batch 1**. Batch 4 on an 11 GB laptop got OOM-killed — the harness now streams pages one at a time and runs under a `systemd-run` memory cap.

### What this means for the pipeline

1. **The layout model keys on ruling, not ink.** Ruled answer paper is out of distribution: the grid looks like a table (or a chart). Confidence doesn't help — empty ruled pages scored 0.78–0.82 "table", higher than most real answer pages.
2. **Pre-layout cleanup belongs in the worker.** A ~10-line OpenCV pass (morphological opening with long horizontal/vertical kernels, then paint the lines white) turned whole-page crops into tight regions and cut empty-page tokens from ~21k to ~50, without hurting the printed form. → Worth a pluggable pre-layout step if handwritten documents are in scope.
3. **A blank-page gate comes for free.** After cleanup, "no transcribe regions" means skip the page — here that's 14 of 32 pages that would otherwise burn GPU time.
4. **Handwriting recall is the weak spot — and eyeballing overrated it.** Ink recall = ink inside transcribe crops ÷ (that + unread ink that looks like writing), where ink is dark pixels after line removal, minus a border band for the scanner's edge shadow. After cleanup the answer pages score **0.72**; pages I'd called "good" by eye went as low as 0.54 — question lines, underlined final answers and the examiner's margin marks were missing. On one page the working was found but the final answer ("= 0.8072") was not, and **lowering the threshold doesn't recover it**: at 0.05 the only box covering that line is a 0.06 "text" block spanning half the page, and the SDK's `large` merge mode lets it swallow the good formula regions (0.67/0.38/0.43 disappear). **A coverage fallback does:** cropping every unread-writing blob as an extra text region recovers that answer for +1,690 tokens on the 14 answer pages (3,118 → 4,808, still 12% of one-stage) and +20 on the struck-out pages, where a density filter keeps the diagonal strike lines out. If the fallback crops on a page approach the one-stage cost, sending the whole page is the simpler call.
5. **Label routing matters as much as boxes.** Handwriting classified as "chart" goes to passthrough and is never read. Per-document-type label remaps (e.g. chart → transcribe for text-only forms) are part of the design, not an afterthought.
6. **CPU is a sanity check, not a serving option.** The L4 latency number comes in Week 3/5; the token and region findings carry over unchanged because the detector output doesn't depend on the device.

## AWS-specific notes

- GPU quota is the planning risk everywhere. Already settled in Week 0: ap-southeast-5 G-instance quota ≥ 4 vCPUs, confirmed by a probe launch; the region offers only g6 (L4), so there is no quota hunting across regions to do.
- The layout model is tiny, so `gpunp-layout` is CPU/orchestration-bound rather than GPU-bound — the CPU numbers above are the lower bound on why that node should be sized by vCPU count.

## Review questions (self-check)

1. *Which component plays the voice-activity detector, and why?* The layout detector — it isolates regions worth transcribing and discards empty space, exactly as VAD discards silence before ASR.
2. *Why does CTC need a blank?* To separate genuine repeated characters from one character spread across several slices, and to label slices that contain no character.
3. *Two reasons to pick two-stage over a single OCR VLM?* Lower hallucination scope (each crop is read independently and traces back to a box) and selective, cheaper extraction (send only tables or text regions, never whitespace) — plus batching-friendly request shapes.
4. *100 pages at 6,000 tokens/page?* 600,000 prefill tokens; at ~1,000 tokens/page (compressed encoder) it is ~100,000.
5. *Why does model-vs-system matter when comparing against a frontier API?* A PDF upload to an API hides a whole pipeline (rendering, layout, routing, batching, retries). Owning that system buys control over cost, latency, data residency and tuning that a single model call cannot.

## Verification

- `eval/layout-detection/run_layout.py` runs end-to-end on CPU over all 32 pages under a 2.5 GB memory cap (peak 1.87 GB) ✅
- Re-run with `--remove-rules` on pages 3–30 and on the cover ✅
- No AWS resources created this week (cluster remains destroyed) ✅
