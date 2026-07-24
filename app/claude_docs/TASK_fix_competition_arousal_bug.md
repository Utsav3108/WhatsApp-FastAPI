# TASK: Fix intent/tone branch-order bug + rebalance arousal vs. patience for competition/banter

## Context

Verified against a real conversation log (Trump persona, cricket/sports trash-talk,
9 turns). Curiosity engine math was traced by hand turn-by-turn and confirmed
CORRECT as implemented — do not touch `classify_curiosity_zone` or
`curiosity_delta`'s formulas as part of this task. The actual bugs are in
`PersonaSession.update()`'s branch-classification order, in
`app/persona/persona_session.py`.

**Symptom observed**: a purely competitive, sports-trash-talk exchange (never a
real personal attack) pushed `arousal` to 100 and triggered a full hard block
("Donald Trump is furious, shut down the conversation") after only 9 turns of
what should have read as spirited banter.

---

## Bug 1 — `Intent.COMPETETION` is currently unreachable whenever tone carries heat

### Root cause (pseudocode of current, broken logic)

```
is_genuine_hostility = (intent in [INSULT, HARMFUL_INTENT]) OR (tone == AGGRESSIVE)
is_sarcasm_flavored  = (intent == SARCASM) OR (tone == SARCASTIC)
has_capacity         = arousal < 70 AND patience > 25
is_playful_sarcasm   = is_sarcasm_flavored AND NOT is_genuine_hostility AND has_capacity
is_hostile_turn      = is_genuine_hostility OR (is_sarcasm_flavored AND NOT is_playful_sarcasm)

// branch order:
IF   intent == COMPLIMENT or tone in [WARM, EXCITEMENT]:      -> compliment_delta
ELIF is_playful_sarcasm:                                       -> banter_delta
ELIF is_hostile_turn:                                           -> hostility_delta   // <-- intercepts here
ELIF intent == APOLOGY:                                         -> apology_delta
ELIF intent == COMPETETION:                                      -> competition_delta // <-- never reached
   with tone != Neutral
ELIF tone == VULNERABLE:                                         -> vulnerable_delta
ELIF intent in [CONVERSATION, ASK]:                              -> conversation_drain
```

Because `is_genuine_hostility` fires on `tone == AGGRESSIVE` alone (no intent
check), and `is_sarcasm_flavored` fires on `tone == SARCASTIC` alone, ANY
`Intent.COMPETETION` message delivered with an aggressive or sarcastic tone gets
swallowed by an earlier branch before it ever reaches `elif intent ==
COMPETETION`. In a trash-talk conversation, competitive messages are delivered
with heat almost by definition — so `competition_delta` (the formula
specifically designed to be gentler than real hostility) is effectively dead
code in practice. Confirmed directly against the log: a `COMPETETION +
Aggressive, intensity=75` turn used `hostility_delta`'s 1.5x tone multiplier
(`arousal += 33.75`) instead of `competition_delta`'s 0.4x weighting (`arousal
+= 9.0`) — the difference between landing around 78 and hard-clamping to 100.

### Required fix — intent must outrank tone for competition/sarcasm framing

```
is_genuine_attack     = intent in [INSULT, HARMFUL_INTENT]   // tone-independent, always wins, unchanged
is_competitive        = intent == COMPETETION
is_sarcasm_flavored   = intent == SARCASM or tone == SARCASTIC
has_capacity          = arousal < 70 AND patience > 25
is_playful_sarcasm    = is_sarcasm_flavored AND NOT is_genuine_attack AND NOT is_competitive AND has_capacity
is_aggressive_tone_only = tone == AGGRESSIVE AND NOT is_competitive AND NOT is_genuine_attack
                          // aggressive tone with no competitive or insult
                          // framing behind it — the ONLY remaining path into
                          // plain hostility_delta on tone alone

is_hostile_turn = is_genuine_attack
                  OR is_aggressive_tone_only
                  OR (is_sarcasm_flavored AND NOT is_playful_sarcasm)

// NEW branch order — competitive framing now checked before the
// hostility/sarcasm fallbacks, so it can never be pre-empted by tone alone:
IF   intent == COMPLIMENT or tone in [WARM, EXCITEMENT]:  -> compliment_delta
ELIF is_competitive:                                       -> competition_delta   // NEW POSITION — checked early,
                                                                                    // regardless of Aggressive/Sarcastic tone riding along
ELIF is_playful_sarcasm:                                    -> banter_delta
ELIF is_hostile_turn:                                        -> hostility_delta
ELIF intent == APOLOGY:                                      -> apology_delta
ELIF tone == VULNERABLE:                                      -> vulnerable_delta
ELIF intent in [CONVERSATION, ASK]:                            -> conversation_drain
```

Note `Intent.COMPETETION` branch is deleted from its old position (was
unreachable dead code below `is_hostile_turn` anyway) and moved up, checked
right after compliments. `is_genuine_attack` (real insults) still always wins
over everything — a genuine `Intent.INSULT` delivered inside trash-talk framing
should still land as a real attack, not competition.

**Also update**: the `is_hostile_turn` flag feeds `curiosity_delta`'s flat -20
hostile-turn penalty and `is_new_topic`/`topic_repeat_streak` tracking
downstream — confirm competitive turns no longer trip that penalty once this
fix lands (they shouldn't; `is_competitive` messages are excluded from
`is_hostile_turn` in the new logic above).

---

## Bug 2 — arousal is overweighted vs. patience for competition/banter

### Reasoning (keep as a code comment near both formulas)

Arousal should model *threat detection* — "am I under attack." Sarcasm and
competitive banter aren't threats, they're **effortful**: parrying jabs and
keeping ego-sparring going costs energy/stamina, not vigilance. That maps onto
patience (a depleting resource) far more naturally than arousal (a threat
gauge). Currently both formulas still put meaningful weight on arousal —
rebalance so patience carries the primary cost, arousal only a small residual.

### Required fix — pseudocode for both formulas

```
FUNCTION competition_delta(threat_sensitivity, self_regulation, intensity):
    // OLD: arousal += (threat_sensitivity/100) * intensity * 0.4   (dominant cost)
    // NEW: arousal weight cut hard, patience becomes the primary cost
    arousal_delta  = (threat_sensitivity / 100) * intensity * 0.1   // small residual — still real, no longer dominant
    patience_delta = -(intensity * 0.35) / max(self_regulation, 1)   // the actual cost: banter is tiring, not threatening
    mood_delta     = intensity * 0.08                                // still a bit fun, slightly higher than before
    RETURN {arousal: arousal_delta, patience: patience_delta, mood: mood_delta}

FUNCTION banter_delta(threat_sensitivity, self_regulation, intensity):
    // OLD: arousal += (threat_sensitivity/100) * intensity * 0.3
    // NEW: same direction of shift as competition_delta
    arousal_delta  = (threat_sensitivity / 100) * intensity * 0.05  // near-zero — genuine roasting is not a threat signal
    patience_delta = -(intensity * 0.35) / max(self_regulation, 1)   // primary cost, slightly higher than the old 0.3 weighting
    mood_delta     = intensity * 0.1                                 // unchanged — a good roast is still fun
    RETURN {arousal: arousal_delta, patience: patience_delta, mood: mood_delta}
```

Note both formulas now take `self_regulation` as a signature parameter (already
true for `competition_delta`'s caller in some versions — confirm signature
matches call site in `update()` and update the call if needed, since
`competition_delta` previously only took `threat_sensitivity` and `intensity`).

### Why this matters beyond just "feels more correct"

`has_emotional_capacity()` already gates on both arousal AND patience — with
this rebalance, a long trash-talk session still eventually tips a persona out
of playful-banter mode, just because patience wears thin (an honest "the joke
overstayed its welcome" signal), not because arousal falsely spikes to
threat-detection levels over something that was never actually a threat.

---

## Expected side effect on curiosity (no code change needed here — just verify)

Curiosity's `-20` flat hostile-turn penalty was firing incorrectly on
`COMPETETION` turns whenever tone carried heat, because those turns were
misrouted through `is_hostile_turn` before Bug 1's fix. Once Bug 1 lands,
genuinely competitive-but-friendly turns should stay classified as NOT
hostile, so they no longer trip that penalty — curiosity should accumulate
more smoothly through a banter-heavy conversation like the one in the log.
**Do not add a separate fix for this** — just re-run the same test conversation
after Bug 1 + Bug 2 land and confirm curiosity climbs past the 35-point
"mildly intrigued" threshold at some point in a 9-turn friendly trash-talk
exchange, where previously it topped out around 25.

---

## Test plan

1. **Regression test — re-run the exact 9-turn cricket/sports trash-talk log**
   this task is based on (paste the log into a test or fixture). Confirm:
   - Arousal never reaches the 100 hard-block threshold across the same 9
     turns, given the same intent/tone/intensity sequence.
   - No turn misroutes a `COMPETETION` intent into `hostility_delta` —
     assert on which delta function fired per turn if the test harness
     allows instrumenting that.
   - Final curiosity value is higher than the old log's ~25, since fewer
     turns incorrectly trip the -20 hostile penalty.

2. **Unit test — genuine attack still wins.** `Intent.INSULT` with
   `Tone.NEUTRAL` (deadpan insult) must still route to `hostility_delta`, not
   `competition_delta`, confirming `is_genuine_attack`'s precedence is intact.

3. **Unit test — competitive + aggressive tone routes correctly.**
   `Intent.COMPETETION` + `Tone.AGGRESSIVE`, high intensity, must route to
   `competition_delta`, and the resulting arousal delta should be
   substantially smaller than what `hostility_delta` would have produced for
   the same inputs (assert the specific formula, not just "less than
   hostility" in the abstract — pin the exact 0.1 vs. 1.5 multiplier
   difference).

4. **Unit test — pure aggressive tone, no competitive/insult intent, still
   reads as hostile.** e.g. `Intent.CONVERSATION` + `Tone.AGGRESSIVE` should
   still fall through to `is_aggressive_tone_only` → `hostility_delta`. This
   confirms the fix narrows the hostility gate correctly rather than
   accidentally disabling it for all aggressive tone.

5. **Unit test — playful sarcasm without competitive intent still routes to
   banter_delta as before** (e.g. `Tone.SARCASTIC` alone, capacity present,
   no `COMPETETION`/`INSULT` intent) — confirms Bug 1's fix doesn't
   regress the existing sarcasm-banter path.