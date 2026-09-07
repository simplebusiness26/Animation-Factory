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

The existing SDXL + IP-Adapter workflow remains available only as a fallback if the primary free model cannot run or repeatedly fails.

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
