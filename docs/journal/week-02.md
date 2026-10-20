# Week 2 — SOTA OCR & Visual Document Understanding

**Focus:** why this pipeline is two-stage (layout detector → VLM transcriber) rather than one big page-level VLM. A design week: no code or cloud infrastructure changes — the cluster stays destroyed, $0 spend.

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

## AWS-specific notes

- GPU quota is the planning risk everywhere. Already settled in Week 0: ap-southeast-5 G-instance quota ≥ 4 vCPUs, confirmed by a probe launch; the region offers only g6 (L4), so there is no quota hunting across regions to do.
- The layout model is tiny (~33M params, encoder-only), so `gpunp-layout` is CPU/orchestration-bound rather than GPU-bound — that node should be sized by vCPU count.

## Review questions (self-check)

1. *Which component plays the voice-activity detector, and why?* The layout detector — it isolates regions worth transcribing and discards empty space, exactly as VAD discards silence before ASR.
2. *Why does CTC need a blank?* To separate genuine repeated characters from one character spread across several slices, and to label slices that contain no character.
3. *Two reasons to pick two-stage over a single OCR VLM?* Lower hallucination scope (each crop is read independently and traces back to a box) and selective, cheaper extraction (send only tables or text regions, never whitespace) — plus batching-friendly request shapes.
4. *100 pages at 6,000 tokens/page?* 600,000 prefill tokens; at ~1,000 tokens/page (compressed encoder) it is ~100,000.
5. *Why does model-vs-system matter when comparing against a frontier API?* A PDF upload to an API hides a whole pipeline (rendering, layout, routing, batching, retries). Owning that system buys control over cost, latency, data residency and tuning that a single model call cannot.

## Verification

- No code or infrastructure changes this week; no AWS resources created (cluster remains destroyed) ✅
