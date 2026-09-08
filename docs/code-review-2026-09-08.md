# Animation Factory code review — 8 September 2026

Reviewed branch `main` at `b568cf2` (bridge, controller chain v1–v6, pipeline modules, Kaggle kernels, workflows, tests, and the persisted Kaggle failure logs). Production remains paused; nothing here submits a notebook.

## Bugs fixed in this review

| Severity | Defect | Fix | Regression test |
| --- | --- | --- | --- |
| High | `kernel_output` builds `artifacts/<slug>` and calls `shutil.rmtree` on it. `KERNEL_RE` accepted `..` as a slug, so `{"action":"kernel_output","kernel":"owner/.."}` would delete the whole checkout in CI. A leading `-` could also be parsed as a Kaggle CLI flag. | Slugs and owners must start with an alphanumeric character. | `test_kernel_ref_cannot_name_parent_directory_or_flag`, `test_kernel_output_never_deletes_outside_artifacts` |
| High | The motion runner requested LTX-Video's extra as `[inference-script]`; the package only defines `[inference]`. pip warns and skips `imageio[ffmpeg]`, `av` and `torchvision`, so the LTX path cannot write video. The clone also tracked a moving `main`. | Use `[inference]`; pin the checkout to `4b2d0530…` (verified to still ship `configs/ltxv-2b-0.9.6-distilled.yaml`). The legacy `shot-runner` also gained the missing `sys.path` insert. | Kaggle-only; not testable locally |
| Medium | `safe_repo_file` only checked the textual prefix, so `shows/../control/command.json` passed the `shows/` restriction. | The resolved path must sit under one of the allowed roots. | `test_repo_file_root_cannot_be_escaped_with_dotdot` |
| Medium | `retry_motion` built the Kaggle folder outside its `try`. A packaging failure (uncommitted stills, unapproved batch) escaped the controller with unsaved state instead of being recorded as a submit failure. | Build inside the `try`; guard the cleanup. | `test_motion_packaging_failure_is_recorded_not_raised` |
| Medium | `safe_status` treated any exception text containing `404` as a missing notebook. Retry slugs are timestamp-derived (`…-r1-8404127`), so a transient status error on such a kernel would be misread as MISSING and trigger a replacement submission. | Match `404` only as a standalone token. | `test_status_error_mentioning_slug_digits_is_not_missing` |
| Low | `pipeline/` was a namespace package. On Kaggle any installed regular package named `pipeline` would shadow it and break the still runner's imports. | Add `pipeline/__init__.py` and ship it in the pinned snapshot. | Existing snapshot tests copy the new file |
| Low | `artifacts/`, `result.md` and `dist/` were not ignored; the README described `worker.py` as the workflow entrypoint. | `.gitignore` and README updated. | — |

Suite: 40 tests pass. All entrypoints compile; skill/canon validators pass.

## Root cause of the recorded motion failures

The persisted `motion-error-*` manifests show every shot failing in the same way:

1. `ModuleNotFoundError: No module named 'ltx_video'` — an editable install is only visible to a new interpreter. The `sys.path` insert added in the previous review addresses this, and the extra-name fix above makes the install complete.
2. `cannot import name 'is_offline_mode' from 'huggingface_hub'` on both diffusers fallbacks — the fallback path runs `pip install --upgrade diffusers …` after LTX has pinned `huggingface-hub~=0.30`. diffusers 0.40 requires `huggingface-hub>=1.23,<2`; LTX-Video requires `huggingface-hub~=0.30` and `transformers<4.52`. **These two stacks cannot coexist in one interpreter.** Whichever installs second breaks the other.

That conflict is a design problem, not a pin problem, so it is not patched here.

## Recommended improvements (not applied)

1. **Isolate the video backends.** Run LTX in its own virtualenv (`python -m venv --system-site-packages /kaggle/working/ltx-venv`) and invoke `inference.py` as a subprocess, or drop the diffusers fallbacks from the LTX kernel and run them as a separate fallback kernel. Pin the fallback stack to the same versions as `kernels/reference-still-runner/requirements.txt` and remove `--upgrade`.
2. **Restore a runnable restart path.** `autonomous-episode-001.yml` is now an always-skipped stub. The pre-pause workflow (see `git show 64d9f08^:.github/workflows/autonomous-episode-001.yml`) installed ffmpeg, espeak-ng, edge-tts and numpy, ran the controller on a schedule, and committed state/stills. Nothing in the repo does that today, so "unpause" currently means re-creating that workflow by hand. Commit a disabled-by-default version that points at `episode001_orchestrator_v6.py` and installs the renderer dependencies.
3. **Collapse the controller chain.** v3–v6 monkey-patch each other's module attributes at import time (`v2.retry_motion = …`, `base.stage_generated_stills = …`). Behaviour depends on import order and the tests must reach through `v3._ORIGINAL_RETRY_MOTION` to test the raw function. v5's handlers are fully overridden by v6 and are dead. One module with explicit composition would be much easier to reason about.
4. **Persist per-shot progress.** Both kernels write incremental reports, but the controller still treats a batch as all-or-nothing; a single failed still or clip re-renders everything. Staging successful shots and re-submitting only the failed IDs would honour the "repair the smallest unit" rule in `AGENTS.md`.
5. **Kaggle-side `kernel_status` for `run_shot`.** `worker_v2` tolerates the private session-status 403 for `run_kernel` only; `run_shot` still fails the whole command after a successful push.
6. **Double download on kernel ERROR.** `_diagnostic_signature` and the wrapped v2 handler both call `persist_kernel_diagnostics` with the same label, downloading the notebook output twice per poll.
7. **Video dimensions.** The motion job uses 704×400. LTX pads non-multiples of 32 internally, but 704×384 or 704×416 avoids the pad/crop and matches the LTX VAE grid; the reduced profile hard-codes the same 400.
8. **Renderer dependencies fail late.** `render_episode001.py` falls back from edge-tts to espeak-ng, but a missing espeak binary raises `FileNotFoundError` after all voices have been attempted. Check both TTS routes before starting ffmpeg work, and mark the espeak fallback in the QA report so a robotic-voice render cannot be mistaken for the intended audio.
9. **Reference resolution.** The five locked character crops are 82–84 × 103 px. They pass integrity checks but give FLUX very little identity signal at 1024 px. Higher-resolution approved crops would improve continuity more than any prompt change.
10. **Prompt scope.** Most motion prompts still ask for four or five simultaneous actions plus a camera move, against the one-primary-action rule. Splitting them before the next GPU run is cheaper than repairing the clips afterwards.
