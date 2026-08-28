# Animation Factory — Kaggle Worker

This repository contains a secure bridge that lets ChatGPT control approved Kaggle operations indirectly through the connected GitHub account.

## Control flow

ChatGPT -> `control/command.json` -> GitHub Actions -> Kaggle CLI/API -> Kaggle notebook/GPU -> `results/latest.md` + workflow artifact

Only users with repository push access can change the command file. The worker does not accept arbitrary shell commands.

## One-time setup

In this repository, open **Settings -> Secrets and variables -> Actions**.

1. Add a repository secret named `KAGGLE_API_TOKEN` containing the token generated from Kaggle Settings > API. Modern Kaggle tokens begin with `KGAT`.
2. Add a repository variable named `KAGGLE_OWNER` containing your Kaggle username/owner slug.

Do not commit either value into this repository.

## Supported commands

Commands are written into `control/command.json`. Include a new `request_id` each time so GitHub receives a new commit.

### Test authentication

```json
{
  "action": "ping",
  "request_id": "ping-001"
}
```

### Search models

```json
{
  "action": "search_models",
  "query": "text to video",
  "limit": 10,
  "request_id": "models-001"
}
```

### Search datasets

```json
{
  "action": "search_datasets",
  "query": "animation",
  "limit": 10,
  "request_id": "datasets-001"
}
```

### Search notebooks

```json
{
  "action": "search_kernels",
  "query": "diffusion video",
  "limit": 10,
  "request_id": "kernels-001"
}
```

### Run a repository kernel

```json
{
  "action": "run_kernel",
  "path": "kernels/smoke-test",
  "accelerator": "NvidiaTeslaT4",
  "request_id": "run-001"
}
```

### Check status

```json
{
  "action": "kernel_status",
  "kernel": "YOUR_KAGGLE_USERNAME/animation-factory-bridge-smoke-test",
  "request_id": "status-001"
}
```

### List output files

```json
{
  "action": "kernel_files",
  "kernel": "YOUR_KAGGLE_USERNAME/animation-factory-bridge-smoke-test",
  "request_id": "files-001"
}
```

### Download outputs

```json
{
  "action": "kernel_output",
  "kernel": "YOUR_KAGGLE_USERNAME/animation-factory-bridge-smoke-test",
  "request_id": "output-001"
}
```

Downloaded files are uploaded as a temporary GitHub Actions artifact named `kaggle-output`. Text status is written back to `results/latest.md`.

## First GPU test

The included `kernels/smoke-test` script writes a small JSON report showing whether Kaggle assigned a GPU and which GPU it sees. The worker uses a T4 request for the first test rather than P100 because current Kaggle CLI documentation warns that the default Kaggle image can fail CUDA workloads on P100.
