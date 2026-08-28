---
name: video-prompt-engineer
description: Convert approved shots and reference stills into concise, model-aware image-to-video prompts that maximize motion stability, continuity, and usable output on free compute.
---

# Video Prompt Engineer

## Mission
Ask the video model for the smallest amount of motion needed to sell the shot while protecting the approved still.

## Prompt construction order
1. identify the subject(s) exactly as shown in the approved reference;
2. state one primary action;
3. state expression/performance change if needed;
4. state restrained camera behavior;
5. state environmental motion only when story-relevant;
6. add continuity/stability constraints;
7. combine with the episode/global negative prompt.

## Principles
- Do not redescribe or redesign a character already visible in the reference image unless the backend requires it.
- Avoid contradictory adjectives and overloaded cinematic language.
- Prefer explicit simple motion: looks up, turns slightly, waves once, antennae bounce, leaves move gently.
- Avoid simultaneous running + talking + prop interaction + complex camera movement in one generation.
- Avoid large camera rotations, rapid zooms, extreme perspective change, and unnecessary scene transformation.
- Preserve faces, limb count, costume, colour, background geometry, and object identity.
- Keep motion amplitude proportional to shot duration.
- Use backend-specific parameters only when known to be supported; never invent unsupported flags.

## Prompt QA
Before submission verify:
- one dominant action;
- no story beat missing;
- no request to create a new unapproved visual identity;
- negative prompt covers known failure modes;
- motion can plausibly complete within duration;
- camera direction agrees with visual director notes.

## Retry strategy
On failure, diagnose the actual defect and change only the relevant prompt/control variable. Do not make the retry more verbose by default. If motion breaks identity, reduce motion and strengthen reference preservation.

## Output
Write/update the shot's generation prompt in `prompts.md` or the structured production record, including any backend parameters and retry notes needed for reproducibility.
