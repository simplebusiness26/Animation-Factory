---
name: shot-planner
description: Convert an approved animation script into generation-friendly shots with clear actions, durations, continuity requirements, and edit purpose.
---

# Shot Planner

## Mission
Break the approved script into the smallest set of strong shots needed to tell the story clearly and generate reliably.

## Shot design rules
- Give every shot one primary story beat and one primary motion idea.
- Prefer 4–8 second generated clips unless a proven backend supports a longer stable take.
- Avoid asking one clip to perform several sequential actions, major camera moves, or location changes.
- Specify who is visible, where they are, what they are doing, the emotional expression, framing, camera motion, and the edit purpose.
- Reuse established angles and approved reference assets when this improves continuity.
- Create a new still/reference target before motion generation when a new composition is required.
- Maintain screen direction and relative character positions across adjacent shots unless the cut intentionally resets geography.
- Plan cutaways/reaction shots when they can hide generation limitations or make the comedy clearer.

## Required shot fields
For each shot capture:
- id;
- duration;
- location;
- characters;
- story beat;
- framing/camera;
- primary action;
- expression/performance;
- continuity dependencies;
- reference-still requirement;
- audio/dialogue cue;
- transition/edit note.

## Generation feasibility gate
Reject or split a shot if it requires:
- multiple complex character interactions at once;
- dramatic object transformations;
- uncontrolled crowd motion;
- extreme camera movement plus character action;
- precise lip sync when the production does not require it;
- continuity that cannot be anchored to an approved reference.

## Output
Write/update `shot-list.md` and ensure `production.json` contains a matching shot inventory. Preserve approved shot IDs wherever practical so downstream assets remain addressable.
