---
name: episode-qa
description: Inspect generated shots and finished episodes for continuity, anatomy, motion, story readability, audio, and technical defects; trigger targeted automatic repair before release.
---

# Episode QA

## Mission
Catch defects before the user has to point them out, and repair the smallest possible unit automatically.

## Shot gate
Score each generated shot from 1–5 for:
- character identity/continuity;
- anatomy and object integrity;
- motion stability;
- background/set stability;
- composition/readability;
- story/performance accuracy;
- technical cleanliness.

A shot is blocked immediately by any critical defect, including:
- wrong recurring character identity, colour, costume, scale, or signature features;
- extra/missing limbs or severe face deformation;
- obvious character/object melting or duplication;
- major background morphing that breaks the scene;
- action contradicts the planned beat;
- visible watermark/text artifact;
- frightening/unsafe unintended imagery;
- unusable corruption, frozen output, or broken encoding.

## Pass rule
Unless a production file overrides it:
- no critical defects;
- every category >= 4/5;
- overall average >= 4.2/5.

## Targeted repair loop
When a shot fails:
1. identify the exact defect and probable cause;
2. preserve every element that already works;
3. choose the smallest repair: trim, prompt adjustment, reduced motion, stronger reference, new still, or full shot regeneration;
4. increment the shot attempt count;
5. regenerate only the failed unit;
6. run the shot gate again.

Continue automatically until pass or the configured attempt limit is reached. Do not ask the user to choose between routine retry variants.

## Final episode gate
Review the assembled episode for:
- story understandable from start to finish;
- character appearance and voice consistency;
- recurring location/prop continuity;
- pacing and comic timing;
- dialogue intelligibility and mix balance;
- abrupt visual/audio jumps;
- duplicated/missing shots;
- beginning/end completeness;
- target runtime/aspect ratio/export correctness.

## Release status
Use one of:
- `PASS` — release-ready;
- `REPAIR` — precise automatic repairs required;
- `ESCALATE` — repeated automatic repair exhausted or a genuinely creative decision is unresolved.

Never label an episode complete while a blocker remains.
