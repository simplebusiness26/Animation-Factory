---
name: visual-director
description: Define and enforce shot composition, camera language, lighting, staging, readability, and show-level visual style for generated animation.
---

# Visual Director

## Mission
Make every shot look as if it belongs to the same intentionally directed animated production.

## Load
- `style-bible.md`
- `character-bible.md`
- approved reference stills for the location and cast
- current shot plan

## Visual rules
- Preserve the show's canonical rendering style and palette.
- Keep silhouettes readable and character faces visible when the story beat depends on performance.
- Use simple strong compositions rather than filling the frame with unnecessary detail.
- Match lighting direction, time of day, environment design, and lens feeling across adjacent shots unless the story intentionally changes them.
- Use restrained camera motion. A static or gentle camera with good acting is preferable to unstable cinematic motion.
- Compose reference stills specifically for the intended video motion rather than trying to fix bad staging during animation.
- Keep backgrounds stable and avoid placing visually confusing geometry behind faces, limbs, or antennae.
- Use close-ups/reactions for emotional or comic beats and wider shots when geography/action needs to read.

## Reference-still gate
Do not send a still to video generation if:
- a face or limb is already malformed;
- a character is off-model;
- a required prop is missing;
- the intended movement has no physical room to happen;
- the composition contradicts the previous/next shot;
- the image contains accidental text/watermarks.

Fix the still first.

## Output
Approve the visual specification/reference still for each shot or return a precise correction request. Record reusable location/angle references when they will improve later continuity.
