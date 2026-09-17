# MiniMax H3 isolated experiment

This experiment adds MiniMax H3 without changing Animation Factory's production video backend.

## Why it is separate

The existing `run_shot` path and its LTX/I2VGen/SVD fallback chain remain untouched. MiniMax runs through a separate command file, worker, workflow and Kaggle kernel. This makes A/B testing safe and reversible.

## Control path

`control/minimax-command.json -> .github/workflows/minimax-h3-test.yml -> minimax_worker.py -> Kaggle -> kernels/minimax-h3-test/main.py`

The experiment reuses the existing `KAGGLE_API_TOKEN` secret and `KAGGLE_OWNER` repository variable.

## Start a test

Use an approved Episode 001 shot. Example:

```json
{
  "action": "run_minimax_shot",
  "shot": "001",
  "request_id": "minimax-h3-e001-s001-test-1"
}
```

The worker reads the existing Episode 001 motion job and approved still from the repository. The chat/controller cannot inject arbitrary prompts or paths.

## Retrieve output

After the Kaggle kernel completes, set the command to:

```json
{
  "action": "kernel_output",
  "kernel": "YOUR_KAGGLE_OWNER/minimax-h3-e001-s001",
  "request_id": "minimax-h3-e001-s001-output"
}
```

Expected output files:

- `minimax-h3-test.mp4`
- `minimax-h3-report.json`

The report records the model, GPU, frame count, dimensions, native-audio status, runtime and any loader/OOM failure.

## Hardware note

MiniMax H3 is much heavier than the current Animation Factory video models. The test kernel uses a community FP8/Turbo package intended for free-cloud T4 experimentation and automatically records failure diagnostics. A failed T4 test should not be treated as a failure of H3 itself; it may indicate that the free Kaggle hardware or current quantized package is insufficient.

## Promotion rule

Do not add H3 to production fallbacks until an A/B test demonstrates acceptable:

1. character and costume continuity;
2. controlled motion;
3. background stability;
4. render reliability on available hardware;
5. runtime/quota cost;
6. useful native audio without damaging dialogue planning.
