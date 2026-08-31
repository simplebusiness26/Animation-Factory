# Earth Needs Help — Character Continuity Bible

This file is the textual companion to the approved visual reference pack. **Approved character reference images override all prose, storyboard derivatives, generated stills, and later guesses.**

## Canon authority

Use canon in this order:
1. locked approved individual character reference image;
2. locked approved full-cast reference image;
3. this `character-bible.md`;
4. approved earlier production frames;
5. script / shot description.

A storyboard, attractive generation, prompt, or later model output may never redesign a recurring character.

## Global continuity rules

- Every visual generation must load the continuity manifest and the reference image(s) for every recurring character visible in the shot.
- Do not use text-only prompting as the identity mechanism for recurring characters.
- Do not redesign recurring characters between shots or episodes.
- Keep signature colours, silhouette, face/eyes, head features, wardrobe, accessories, material treatment, and relative scale stable.
- Expressions, pose, camera angle, lighting, and action may change; identity may not.
- When a required reference image is missing, **stop generation rather than inventing the character again**.
- A generated still does not become production-ready until continuity QA passes.

## Locked main cast

These colour/shape identities come from the original asset labelled **MAIN CHARACTERS — CONSISTENCY REFERENCE**. Later derivative storyboards that conflict with this mapping are not canon.

### Captain Pip

**Canonical identity:** green alien captain; rounded head; large expressive eyes; unmistakable captain/leader styling.

**Must not change:** green identity colour, rounded head language, large-eye facial design, captain identity, approved clothing/hat/insignia from the visual reference, and established proportions.

**Performance:** brave, positive, serious about every rescue, naturally comic because small problems are treated as major emergencies.

### Bloop

**Canonical identity:** blue, round alien; antennae; huge expressive eyes; soft friendly silhouette.

**Must not change:** blue identity colour, round body, antennae, huge-eye face design, approved limb/body proportions and any visual details shown in the locked reference.

**Performance:** excitable, curious, hungry, funny, big-hearted.

### Zig

**Canonical identity:** purple, tall/slim alien inventor; expressive face/eyebrow design; recurring inventor/gadget identity.

**Must not change:** purple identity colour, tall slim silhouette, approved face/head design, approved recurring wardrobe/accessories, and established proportions.

**Performance:** clever, inventive, enthusiastic, overcomplicates simple problems.

### Momo

**Canonical identity:** pink, small alien; large ear/head-side features; calm thoughtful face and friendly rounded design.

**Must not change:** pink identity colour, small scale, large ear/head-side silhouette, approved face/body design, and any approved recurring clothing/accessories.

**Performance:** kind, smart, calm, usually finds the simple solution.

## Human child

The recurring Earth child must also use a locked visual reference once present. Hair, face, skin tone, clothing, backpack, shoes and proportions may not drift between shots.

Until that visual reference is committed and marked locked in `continuity-manifest.json`, shots requiring the child must not be regenerated as final production stills.

## Scale relationships

Exact scale comes from the locked full-cast reference. Never infer new relative sizes from a fresh generation. Once the reference pack is locked, those proportions are reused for every shot.

## Reference policy

Machine-readable enforcement lives in `continuity-manifest.json`.

Required recurring-character assets live under:

`shows/earth-needs-help/assets/characters/`

Expected files:
- `captain-pip.png`
- `bloop.png`
- `zig.png`
- `momo.png`
- `human-child.png`
- `full-cast.png`

The system must fail closed if a required character reference is absent. The existing Episode 001 generated stills 002–009 are **not canonical reference material** and must not be used to teach later shots what the cast looks like.
