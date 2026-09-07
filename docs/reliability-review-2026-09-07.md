# Animation Factory reliability review — 7 September 2026

Reviewed `main` at `9e779b355bf1a96055052a45e80ad7160bcf5120` (the hybrid-image upgrade), including its controller, bridge, image runner, motion handoff, assembly and release checks.

**Verdict: the original update was not ready for unattended production.** Its green CI checked syntax, JSON and skill configuration, but missed runnable integration failures. This review repairs the defects below and adds regression coverage. Production stays paused; no Kaggle notebook or paid generation was started.

## Findings and repairs

| Severity | Verified defect | Repair |
| --- | --- | --- |
| High | The v3–v6 controller chain calls `v2.main()`, but that function does not exist. The normal waiting path raises `AttributeError`. | Restore phase dispatch and exercise the real controller entrypoints in tests. |
| High | The still-retry path uses the old SDXL directory, ignoring the newly configured FLUX runner. | Read the configured image runner, validate the whole image job and prepare that runner before submission. |
| High | Generic `reference-still-runner` submissions lack the Episode 001 name markers; `run_shot` also bypasses the pause check. Controller entrypoints do not consistently honour the persisted pause. | Enforce pause/repair gates before submission, preserve paused state, and fail closed on missing or malformed state. Read-only checks remain available. |
| High | Passing the actual episode image job to the router returns `ready` with **zero** references because it ignores the nested shots. A nonexistent imported file can also be called ready. The runner ignores per-shot routes. | Validate all nine shot entries and 40 reference uses, honour per-shot routes, and require a readable, hash-bound, visually approved import. Block unsupported fallback execution. |
| High | Image and motion bootstraps fetch changing `main` files; motion can download different stills from those whose hashes were reviewed locally. | Pin source, job and assets to one committed revision. Verify the motion inputs against the approval at that revision. Read the live pause separately. |
| High | The image runtime installs moving Diffusers source and open-ended library versions. | Pin model-facing library versions and the model checkpoint revision. This improves reproducibility; it is not a GPU compatibility certificate. |
| High | A saved PNG is treated as successful even if numerical failure creates blank/invalid output. Incomplete batches can archive or replace existing assets before all files validate. | Check raw output pixels and dimensions; include per-file SHA-256 values; validate complete reports before staging/archive. Preserve the existing Shot 001 rather than replacing it with an old embedded thumbnail. |
| High | The bridge can report a successful submission when Kaggle prints a push/quota error but exits with code zero. | Recognize those error responses and report failure. |
| High | Repeated status lookups in one poll can disagree. The approval transition bypasses the newest motion-retry guard. Repeated polls can count the same failed notebook as several failures. | Use one status sample, retain guarded submission on the approval path, hold on unknown/transient status, and count each failed notebook once. Repeated staging failures now stop for repair. |
| High | Any downloaded `*final*.mp4` can be released automatically, without visual/audio approval. The existing final QA only probes duration and streams. | Require final technical checks plus visual/audio approval bound to the exact video hash. Hold the controller at final review. |
| Medium | I2VGen/SVD fallback functions import Diffusers utilities before the function that installs Diffusers; an editable LTX install is not added to the current interpreter's path. | Correct import order and make the installed LTX source importable. Align production fallback names with the implemented backends. |

## Verification

- **35 regression tests pass locally.** The suite covers routing, missing/corrupt references, per-shot manual imports, duplicate/invalid IDs, invalid dimensions, non-finite/blank model outputs, launch guards, controller dispatch, retry/status handling, preservation of Shot 001, complete-batch staging, immutable packaging and release approval.
- Image inputs validate for all nine requested new stills, including 40 per-shot uses of the five locked character references.
- All five reference files decode, match their locked SHA-256 and open as images.
- All seven pinned image package versions were confirmed present in the package index; model import compatibility remains unverified.
- The existing 14-stage/14-gate validator and context-loader check pass.
- All Python entrypoints compile. No inference or notebook submission is part of these tests.
- Model inference and Kaggle responses are simulated at their boundaries. The local environment has no PyTorch/GPU runtime; an attempted CPU PyTorch install could not complete because its network approval was cancelled. Model import/inference therefore remains unverified here.

## Remaining production work and quality risks

1. **A controlled Kaggle run is still required after an explicit restart.** Verify the pinned image stack on the assigned GPU, one multi-character still, its visual review, one motion shot, audio/assembly, and artifact retrieval. No current full-run success evidence was found for the new stack. The autonomous/recovery workflows remain disabled by the saved pause; running their present workflow dispatch does not restart production.
2. **Automatic recovery remains batch-based.** Partial image/motion successes are reported, but the controller does not yet persist and resume individual successful shots across fresh notebooks. The new import path can preserve explicitly approved stills, but it does not implement autonomous partial-batch checkpointing. That remains necessary before unattended episode production meets the repository's targeted-repair promise.
3. **GPU fit and precision are unproven.** The runner selects FP16 on T4 and BF16 on newer hardware. Memory use with five image references, the checkpoint's numerical behaviour and the installed Kaggle torch/CUDA stack need a real test. Blank-output detection now prevents silent success; it cannot guarantee the GPU/model combination works.
4. **The video backends still have independent runtime dependencies.** Pinning the new still stack does not certify LTX/I2VGen/SVD compatibility. Their fallback installation, model memory and generated clip quality require separate runtime validation.
5. **The locked character crops are only 82–84 × 103 pixels.** Their integrity is valid, but the available visual detail is limited for a 1024-pixel scene. Higher-resolution approved references would improve the chance of consistent faces and accessories. The existing canon was not replaced.
6. **Several video prompts ask for multiple simultaneous actions and camera moves.** This conflicts with the one-primary-action guidance and raises continuity/motion risks. The final renderer also loops short fallback clips to fill the planned timing. Simplify or split shots based on the first reviewed motion results; a technically playable 80-second export alone is not proof of a good episode.
7. **Review remains a real production stage.** The code does not implement a visual judge that can honestly approve character identity, acting, voices and story quality. Technical validation must not be used as visual approval.

## Primary dependency references

- [Diffusers 0.40.0 FLUX.2 API](https://huggingface.co/docs/diffusers/v0.40.0/api/pipelines/flux2): includes `Flux2KleinPipeline` and multi-reference input support.
- [FLUX.2 Klein 4B model](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B): upstream checkpoint and model information. The configured revision is `e7b7dc27f91deacad38e78976d1f2b499d76a294`.
