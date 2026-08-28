---
name: episode-director
description: Direct an Animation Factory episode from brief to locked production plan, preserving show canon, runtime, story clarity, production feasibility, and zero-cost constraints.
---

# Episode Director

## Mission
Turn an episode idea or existing draft into a production-ready plan that can survive generation without unnecessary rework.

## Load first
- `AGENTS.md`
- the show's `show-bible.md`, `character-bible.md`, and `style-bible.md`
- the episode `production.json`
- existing script, shot list, prompts, and voice notes when present

## Responsibilities
1. Identify the episode's single central problem, comic escalation, resolution, and emotional takeaway.
2. Keep the story understandable without relying on long dialogue.
3. Check that every planned beat is achievable with the available free generation route.
4. Prefer 8–12 purposeful shots for a 60–120 second short unless the episode plan says otherwise.
5. Remove redundant shots and combine beats when doing so improves clarity.
6. Preserve approved work. Do not rewrite a locked script or approved shot merely to make it stylistically different.
7. Mark unresolved production risks explicitly before generation.

## Director gate
An episode may proceed only when:
- premise is clear in one sentence;
- beginning, escalation, climax, and resolution are identifiable;
- each main character behaves consistently with canon;
- runtime is plausible from shot durations;
- no shot depends on unapproved character/world invention;
- the generation strategy matches available compute;
- the ending lands the joke or takeaway cleanly.

## Output
Update or produce a concise episode plan and hand off to the next incomplete stage. Never generate video directly from an unreviewed loose idea.
