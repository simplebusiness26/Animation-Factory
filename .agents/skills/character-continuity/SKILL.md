---
name: character-continuity
description: Enforce canonical character identity, appearance, scale, personality, wardrobe, props, voice continuity, and reference reuse across generated animation shots.
---

# Character Continuity

## Mission
Prevent character drift between shots and episodes.

## Canon priority
Use evidence in this order:
1. approved reference image for the exact character/look;
2. `character-bible.md`;
3. `show-bible.md`;
4. approved earlier episode frames;
5. written episode material.

Never let a new generation override a higher-priority canonical source.

## Before each visual generation
For every visible recurring character verify:
- canonical colour and material/fur/skin treatment;
- silhouette and body proportions;
- face/eye design;
- antennae/hair/head features;
- wardrobe and accessories;
- relative height/scale against other characters;
- required held props;
- personality-appropriate expression and pose.

Build the prompt from canonical identity anchors plus only the changes required for this shot.

## Continuity ledger
For each approved shot record any state that must carry forward, including:
- prop ownership/position;
- dirt/damage/wetness if story-relevant;
- costume state;
- location within the set;
- entrance/exit direction;
- emotional state.

## Failure conditions
A shot fails continuity if a recurring character has an unexplained material change to colour, face, limbs, proportions, costume, signature accessories, relative scale, or personality performance.

Minor lighting variation is acceptable only when identity remains unmistakable.

## Repair behavior
When continuity fails, keep the approved composition/story beat if possible and strengthen identity/reference constraints. Regenerate only the failed shot or failed layer.
