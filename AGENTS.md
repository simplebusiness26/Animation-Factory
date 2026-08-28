# Animation Factory — Agent Constitution

This repository is a production system, not a prompt dump. Agents must preserve continuity, reuse approved assets, and repair failed work before escalating to the user.

## Non-negotiable operating rules

1. Follow the production pipeline in `pipeline/skills.json`; do not skip stages unless the episode explicitly marks them complete.
2. Treat each show's `show-bible.md`, `character-bible.md`, and `style-bible.md` as canonical.
3. Treat approved reference stills and approved audio as stronger evidence than newly generated guesses.
4. Never silently change a character's colour, proportions, clothing, face, voice, personality, scale, recurring prop, or recurring location.
5. Use one clear primary action per generated video shot. Prefer simple, controllable motion over ambitious motion that risks artifacts.
6. Generate from a strong reference still whenever the production strategy says reference-image-to-video.
7. Run QA after every generated shot and again after the assembled episode.
8. If QA fails, diagnose the smallest repairable unit and regenerate only that unit. Do not restart approved work.
9. Automatically attempt repair up to the limit in the episode production file before requesting human input.
10. Preserve the intended story, joke, performance, timing, and emotional beat when repairing a visual defect.
11. Default to zero-cost/open-source production routes. Do not introduce a paid dependency or paid generation service without explicit approval.
12. Never commit credentials, API tokens, private keys, or generated secrets.

## Production order

`episode-director -> scriptwriter -> shot-planner -> character-continuity -> visual-director -> video-prompt-engineer -> generation -> episode-qa (shot gate) -> audio-director -> editor -> episode-qa (final gate)`

A stage may reuse already approved work instead of recreating it.

## Skill loading

Skills live under `.agents/skills/<skill-name>/SKILL.md`.

Before performing a production stage, load the matching skill and the canonical show files. The machine-readable registry is `pipeline/skills.json`.

## Required context for an episode

At minimum load:

- `shows/<show>/show-bible.md`
- `shows/<show>/character-bible.md`
- `shows/<show>/style-bible.md`
- `shows/<show>/episodes/<episode>/production.json`
- the current script, shot list, prompts, and voice notes when present
- any approved reference assets for the affected shot/character/location

## Quality philosophy

The goal is not to produce the most frames. The goal is to produce the best coherent episode within the available free compute. Continuity and clarity outrank spectacle. A simple shot that looks intentional is better than a complex shot with broken anatomy, morphing backgrounds, or inconsistent characters.

## Escalation

Do not ask the user to make routine production decisions that can be resolved from the bibles, episode plan, or prior approved assets. Escalate only when a genuinely creative decision has no canonical answer, a free technical route is exhausted, or repeated automatic repair cannot pass the quality gate.
