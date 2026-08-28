# Earth Needs Help — Visual Style Bible

This file is the visual contract for generated stills and video. It expands the visual language in `show-bible.md` into generation rules.

## Core look

Original polished 3D-style cartoon animation with:
- soft rounded forms;
- expressive readable eyes and faces;
- colourful child-friendly environments;
- tactile but simplified materials;
- gentle cinematic lighting;
- clean silhouettes;
- strong character colour coding;
- stylised rather than photoreal rendering.

The result should feel warm, adventurous, funny, polished, and coherent rather than hyper-detailed.

## Composition

- Make the story beat readable at a glance.
- Keep important faces and hand/prop interactions unobstructed.
- Avoid clutter directly behind antennae, eyes, hands, and small props.
- Use foreground/background separation and simple depth staging.
- Give movement physical room inside the frame.
- Prefer a small number of clearly staged characters over chaotic overlapping poses.

## Camera language

Default to stable, intentional filmmaking:
- static locked camera;
- gentle push/pull;
- small pan/tilt;
- restrained follow movement.

Use rapid orbiting, whip pans, extreme zooms, dutch angles, or large perspective changes only when the story absolutely needs them and the backend has proven it can handle them.

## Lighting

- Soft cinematic key light with readable faces.
- Preserve lighting direction within the same location/time-of-day sequence.
- Avoid crushed shadows, blown highlights, flashing exposure, and dramatic horror lighting.
- Keep character identity colours recognizable under scene lighting.

## Motion

- One dominant motion idea per generated shot.
- Secondary motion may include subtle antenna bounce, blinking, cloth settling, hair/fur response, leaves moving, or small environmental reactions.
- Avoid excessive full-body motion when a reaction or pose change sells the beat.
- Prioritize stable anatomy and recognizable performance over motion quantity.

## Environments

Recurring locations must become reusable sets. Once an angle or key design is approved, retain reference images for later shots and episodes.

For each recurring set lock:
- major layout;
- signature colours/materials;
- important props;
- light direction/time of day;
- scale relative to characters.

## Pilot technical lock

For `001-great-earth-emergency`:
- aspect ratio: 16:9;
- strategy: approved reference still -> image-to-video per shot;
- target clip length: follow `production.json` and split unstable long actions rather than forcing them;
- avoid lip-sync-dependent close-ups unless explicitly planned;
- preserve the episode's global negative prompt across shots.

## Visual rejection conditions

Reject a reference still before animation if it contains:
- off-model recurring characters;
- malformed face/limbs;
- missing signature costume/accessories;
- incorrect relative scale;
- accidental text/watermark;
- scene geometry that makes the intended movement impossible;
- obvious mismatch to the established 3D cartoon style.

## Quality preference

A simpler shot with clean composition, stable identity, and readable acting is preferred over a more spectacular shot with visual instability. Consistency across the episode is part of production value.
