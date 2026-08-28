# Earth Needs Help — Episode 001 Shot 001

Production Kaggle kernel for the first animated shot.

## Chat-controlled flow

ChatGPT updates `control/command.json` → GitHub Actions invokes the Animation Factory worker → worker pushes this bundle to Kaggle with a T4 GPU → Kaggle writes the MP4 and JSON report → Animation Factory retrieves the outputs as a GitHub Actions artifact.

## Bundle

- `input-still.jpg` — locked source frame
- `prompt.txt` — motion direction
- `config.json` — deterministic generation settings
- `main.py` — low-memory I2V runner
- `kernel-metadata.json` — Kaggle execution metadata

The first backend is `ali-vilab/i2vgen-xl` through Diffusers with CPU model offload. No paid model API is required.
