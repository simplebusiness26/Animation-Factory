# Animation Factory Shot Runner Spec v1

## Goal
Let ChatGPT trigger one approved animation shot from this repository without opening Kaggle manually.

Control path:

`ChatGPT -> control/command.json -> GitHub Actions -> worker.py -> temporary Kaggle kernel -> Kaggle T4 -> MP4/report -> GitHub Actions artifact -> ChatGPT`

## Command contract

```json
{
  "action": "run_shot",
  "job_path": "shows/earth-needs-help/episodes/001-great-earth-emergency/jobs/shot-001.json",
  "request_id": "earth-needs-help-e001-s001-v1"
}
```

The chat controller only supplies an allow-listed repository job file. It cannot inject arbitrary shell commands.

## Shot job contract

Each job JSON contains:

- `show`, `episode`, `shot`
- `still_path`: repository-relative PNG/JPG/WebP path
- `prompt`: motion description
- `negative_prompt`
- `duration_seconds` (1-10)
- `fps` (4-24)
- `width`, `height`
- `seed`
- `model`: `ltx-2b-distilled`, `i2vgen-xl`, or `svd-xt`
- `fallback_models`: ordered fallback list

## Automatic asset handoff

The still image is committed once under the show's `assets/stills/` directory. `worker.py` validates the path, copies the binary still into a temporary Kaggle kernel directory, and pushes that directory through the authenticated Kaggle CLI. No phone upload and no manual Kaggle notebook edit are required after an asset is in Animation Factory.

## Kaggle runtime

Default accelerator: `NvidiaTeslaT4`.

Preferred engine: LTX-Video 2B distilled. The official LTX repository provides a 2B distilled checkpoint and image-to-video inference. The runner also keeps prompt-capable I2VGen-XL and Stable Video Diffusion XT fallbacks so a single backend failure does not stop production.

The kernel must:

1. validate CUDA availability;
2. load the job and input still;
3. generate the requested clip;
4. write `/kaggle/working/animation-factory-shot.mp4`;
5. write `/kaggle/working/animation-factory-report.json` with backend, GPU, runtime, dimensions, frame count, seed, and success/error details.

## Output return

`kernel_status` checks the running job.

`kernel_output` downloads the MP4/report/log into a GitHub Actions artifact named `kaggle-output`. ChatGPT can then inspect the report and expose the video artifact to the user.

## Quality gates

A shot is not considered approved merely because generation completed. It must preserve:

- locked character identity and colours;
- locked clothing/accessories;
- correct character count;
- no text/watermarks;
- no frightening or unsafe imagery;
- stable background and anatomy;
- motion that matches the shot prompt.

Failed quality checks are regenerated with a changed seed or reduced motion rather than silently accepted.

## Episode pipeline

`locked references -> still -> run_shot -> quality check -> approved clip -> audio -> assembly`

This is intentionally shot-by-shot so character consistency and comedy timing can be controlled before the episode is assembled.
