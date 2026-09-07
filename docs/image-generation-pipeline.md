# Hybrid Image Generation Pipeline

Animation Factory separates **still-image creation** from **video-shot generation**.

## Definitions

- **Reference / master image:** canonical visual identity for a recurring character, prop, or location.
- **Reference still / keyframe:** the approved static composition that a video model will animate.
- **Video shot:** one continuous generated moving clip from a single camera setup.

## Control flow

`shot plan -> continuity lock -> visual spec -> image route -> reference still -> still QA -> video prompt -> video shot -> shot QA`

## Image routes

### 1. FLUX.2 Klein on Kaggle — default automated route

Configured as `flux2-klein-kaggle` in `pipeline/image-generation.json`.

Primary model: `black-forest-labs/FLUX.2-klein-4B`.

Use for routine stills, backgrounds, bulk generation and automatic retries. Recurring-character shots load the locked reference image for every named recurring character and use multi-reference conditioning. Prompt prose may describe action, expression, camera and environment, but may not override visual identity.

### 2. ChatGPT image account — quality/import route

Configured as `chatgpt-image-account`.

Use for master character references, hero keyframes and difficult continuity rescue. This is deliberately **not** an API call. The image is created using the user's existing ChatGPT image access, then committed into the approved asset path. Once approved, Animation Factory treats it like any other locked production asset.

### 3. SDXL layered fallback

The old SDXL + IP-Adapter implementation is retained for diagnosis. The hybrid router blocks this route until it has a separately validated job; it does not silently run FLUX for a requested SDXL fallback.

## Fail-closed rules

A recurring-character still cannot proceed to motion when:

- a required locked reference is missing or fails its hash check;
- a character is off-model, duplicated, missing or materially redesigned;
- anatomy/face is visibly malformed;
- a required prop is missing;
- the image has accidental text/logo/watermark;
- the composition leaves no room for the intended motion.

## Kaggle runner

`kernels/reference-still-runner/` contains the FLUX.2 batch runner. Episode 001 currently uses:

`shows/earth-needs-help/episodes/001-great-earth-emergency/episode001-image-job.json`

The runner writes one PNG per still plus `animation-factory-image-report.json`. Each still remains `qa_status: pending` until the continuity/visual quality gate approves it.

## Paid-service rule

No paid image API may be introduced or automatically called without explicit user approval. The existing ChatGPT subscription is not treated as API credit.

## Validation and reproducible submission

Run `python -m unittest discover -s tests -v` and the existing canon/skill checks before submitting. The tests replace GPU inference and Kaggle API calls; a pass does not certify model output quality or GPU compatibility.

`python pipeline/image_router.py shows/earth-needs-help/episodes/001-great-earth-emergency/episode001-image-job.json` validates every shot, every used reference hash, dimensions, unique IDs and each shot's selected route. A `ready` plan means the inputs are ready, not that the episode is rendered.

The guarded controller reads `production.json.image_backend.runner`. The bridge prepares this runner when given `run_kernel` with `path: kernels/reference-still-runner`. Both prepare a bootstrap pinned to the current committed source, job, routing configuration and image references. Commit and push changed production inputs before submitting. A separate live pause check still prevents a queued notebook from starting after production is paused.

For an approved ChatGPT image, set the shot's `approved_input_path`, `approved_input_sha256` (the file's SHA-256), and `qa_status: approved`. Approval must come from an actual visual review. The runner reuses the image without loading a model; its staged output still enters the batch continuity review.

The image dependency versions and Hugging Face model revision are pinned. Kaggle's installed PyTorch/CUDA combination is retained and must be verified on its assigned GPU. Generated images are checked for non-finite pixels, blank output, dimensions and file hashes before entering visual QA.

A successful render has `technical_pass` in its final QA report. Publication additionally requires `visual_review: approved`, `audio_review: approved`, and a matching video SHA-256. The controller waits in `awaiting_final_review`; a filename containing `final` cannot authorize publication.

Production remains paused. Neither validation nor this integration change resumes it.
