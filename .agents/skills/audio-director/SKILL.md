---
name: audio-director
description: Direct dialogue, narration, music, sound effects, timing, and voice continuity for Animation Factory episodes using zero-cost/open-source routes by default.
---

# Audio Director

## Mission
Make the episode sound intentional, readable, and consistent without forcing visual generation to solve audio problems.

## Rules
- Preserve a stable voice identity for every recurring character once approved.
- Keep dialogue performances aligned with the character bible and current emotional beat.
- Prefer short clean lines that fit the edit naturally.
- Do not require lip sync unless `production.json` explicitly requires it.
- Use narration only when it improves clarity; do not narrate obvious visible action.
- Use sound effects to sell motion, comedy, impacts, entrances, gadgets, environments, and transitions.
- Keep music supportive rather than masking speech or carrying the entire emotional meaning.
- Default to free/open-source TTS, music, and SFX sources or locally generated audio.

## Audio continuity
Track for recurring voices:
- voice model/source;
- pitch/range character;
- pace;
- energy;
- accent only if canonically specified;
- processing chain and loudness target.

## Mix gate
Before final edit approval verify:
- all speech is intelligible;
- voice identity does not drift;
- SFX align with visible actions;
- music changes support story beats;
- no accidental clipping or huge volume jumps;
- silence is used intentionally rather than filled automatically.

## Output
Update `voice-notes.md` and create/record the audio asset plan for the editor. Reuse approved recurring voice settings rather than recreating them each episode.
