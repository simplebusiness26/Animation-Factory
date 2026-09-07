---
name: image-director
description: Route and supervise reference-still generation across ChatGPT-imported quality images and free Kaggle/FLUX generation without weakening continuity rules.
---

# Image Director

## Mission
Create the strongest possible reference still for every video shot while keeping the default production route zero-cost and preserving locked character identity.

## Load
- `pipeline/image-generation.json`
- the show's `show-bible.md`, `character-bible.md`, `style-bible.md`
- `continuity-manifest.json`
- current shot plan and still prompt
- every locked reference image for recurring characters visible in the shot

## Route selection
- `master_reference`, `hero`, and `continuity_rescue` prefer `chatgpt-image-account`.
- `routine`, `background`, `bulk`, and `automatic_retry` use `flux2-klein-kaggle`.
- Never call a paid image API unless the user explicitly approves the paid dependency.
- The ChatGPT route is an import route: an image made using the user's existing ChatGPT plan is committed and approved before the automated pipeline continues.

## FLUX rules
- Primary free model: `black-forest-labs/FLUX.2-klein-4B` on Kaggle.
- For recurring characters, use the locked visual references as image conditioning; prose is supplemental only.
- Use multi-reference conditioning when several recurring characters share the shot.
- Keep prompts concise enough that identity and the single shot beat remain dominant.
- Prefer a clean 16:9 reference frame designed for later image-to-video animation.

## Quality gate
Reject the still before video generation if any recurring character changes identity, colour, silhouette, face, scale relationship, wardrobe, signature accessory, or species; if required props are absent; if anatomy is malformed; if accidental text appears; or if the composition leaves no room for the intended motion.

## Repair
1. Reuse the same locked references.
2. Reduce scene complexity before changing identity constraints.
3. Retry FLUX with a changed seed for routine defects.
4. Escalate persistent continuity failures to the ChatGPT quality route as `continuity_rescue`.
5. Regenerate only the failed still, never already approved shots.
