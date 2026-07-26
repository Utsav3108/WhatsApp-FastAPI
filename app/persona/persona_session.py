# app/persona/persona_session.py
from datetime import datetime, timezone, timedelta
from app.brain.schemas import Intent, Tone, Topic, Language
from app.brain.emotion_engine import EmotionEngine, clamp, CuriosityZone
from typing import Dict, List, Optional
from app.brain.context import BrainContext
from app.brain.brain_component import BrainComponent


# Maximum length of an auto-expiring block. Both triggers (arousal
# threshold in compile_prompt(), violation count in register_violation())
# use this SAME constant. Change this single value to adjust — no other
# line needs to change.
BLOCK_DURATION_HOURS: float = 1.0


class PersonaSession(BrainComponent):
    def __init__(self, name: str, traits: Dict[str, float], expertise_topics: Optional[List[str]] = None,
                 violation_block_threshold: int = 2, knowledge_cutoff_date: Optional[str] = None):

        self.summary = ""
        self.persona = name

        self.languages = ["english"]

        # Built fresh from structured fields at load() time — never stored
        # as literal text. Empty until hydrated (see load()/_format_user_info
        # below); a session constructed directly (e.g. in tests) simply gets
        # no user_info clause in compile_prompt.
        self.user_info = ""

        # DB identity — None until load()/save() resolve or create a row.
        # PersonaSession itself never opens a DB session; these are plain
        # data the caller uses to hydrate/persist via load()/save().
        self.session_id: Optional[int] = None
        self.ai_persona_id: Optional[int] = None
        self.human_persona_id: Optional[int] = None

        self.threat_sensitivity = traits.get('threat_sensitivity', 50.0)
        self.self_regulation = traits.get('self_regulation', 50.0)
        self.novelty_drive = traits.get('novelty_drive', 50.0)
        self.baseline_security = traits.get('baseline_security', 50.0)
        self.empathic_resonance = traits.get('empathic_resonance', 50.0)

        # Free-text domain descriptions (e.g. "real estate, business deals"),
        # sourced from traits.interests_expertise.expertise — fed directly
        # into the classifier's _detect_topic prompt as the persona's
        # expertise list, not compared against Topic enum members anymore.
        self.expertise_topics: List[str] = expertise_topics if expertise_topics is not None else []

        # ISO date string for historical personas whose knowledge/life ends
        # at a fixed point in time (e.g. "1965-01-24" for Churchill). None
        # for every non-historical persona.
        self.knowledge_cutoff_date: Optional[str] = knowledge_cutoff_date

        self.arousal = max(0.0, 30.0 - (self.baseline_security / 4.0))
        self.patience = min(100.0, 40.0 + (self.self_regulation / 2.0))
        self.mood = 0.0
        self.rapport = 0.0
        self.curiosity = 0.0
        self.curiosity_zone: Optional[CuriosityZone] = None

        self.last_topic: Optional[Topic] = None
        self.last_subject: Optional[str] = None
        self.topic_repeat_streak = 0
        self.turn_count = 0
        self.is_first_turn = True

        # Tracks what flavor of exchange just happened, purely so
        # compile_prompt can hand the LLM a directive tuned to it
        # (e.g. "roast them back" vs "don't get defensive about their
        # vulnerability, but you don't have room for it right now either").
        self.last_turn_context: Optional[str] = None  # 'banter' | 'vulnerable_engaged' | 'vulnerable_dismissed' | None

        # Turn-local, same pattern as last_turn_context: reset False at the
        # top of update(), set True only at the exact moment is_blocked
        # flips False -> True this turn. Read once by socketio_server.py to
        # decide whether to emit 'persona_blocked' for this turn. Never
        # persisted.
        self.just_blocked: bool = False

        self.violation_count = 0
        self.VIOLATION_BLOCK_THRESHOLD = violation_block_threshold

        self.is_blocked = False
        self.block_reason: Optional[str] = None
        self.BLOCK_THRESHOLD = 100
        self.blocked_until: Optional[datetime] = None

        # Decay-calculation anchor. Defaults to "now" at construction time —
        # correct for a brand-new session (nothing has decayed away from
        # anything yet). load() overwrites this from the hydrated row when
        # one exists.
        self.last_emotional_update_at: datetime = datetime.now(timezone.utc)

        # Set True by update()/register_violation() when they actually run
        # this turn. Read by socketio_server.py to decide save()'s
        # state_changed param. Defaults False because a PersonaSession is
        # freshly constructed per message via load() (never cached across
        # turns) — False correctly describes "nothing has mutated yet" at
        # construction/hydration time.
        self.turn_state_mutated: bool = False

    # --- Persistence boundary -------------------------------------------
    # update()/compile_prompt()/_apply()/register_violation() stay
    # completely unchanged, pure in-memory logic. load()/save() are the only
    # two methods aware of the DB — a hydrate/dehydrate boundary around the
    # class, called once per message (not cached across messages), matching
    # the existing "DB sessions open only for brief windows, Gemini calls
    # made outside any open session" discipline already used in
    # socketio_server.py. persona_sessions is deliberately NOT added to the
    # Redis cache layer (app/cache.py) — it's mutated every turn, so a naive
    # TTL cache risks lost-update races on concurrent/cancelled turns.

    @staticmethod
    def _format_user_info(human_persona) -> str:
        """
        Builds the user_info clause fresh from a human persona's structured
        traits + settings — never stored as literal text. `traits` may be a
        legacy free-text string (TraitsType = Union[StructuredTraits, str]),
        in which case there's nothing structured to pull from.
        """
        traits = human_persona.traits
        lines = [f"Name: {human_persona.name}"]

        identity = getattr(traits, "identity", None)
        if identity:
            if identity.profession:
                lines.append(f"Profession: {identity.profession}")
            if identity.nationality:
                lines.append(f"Country: {identity.nationality}")

        city = (human_persona.settings or {}).get("city") if human_persona.settings else None
        if city:
            lines.append(f"City: {city}")

        likes_dislikes = getattr(traits, "likes_dislikes", None)
        if likes_dislikes:
            if likes_dislikes.likes:
                lines.append(f"Likes: {', '.join(likes_dislikes.likes)}")
            if likes_dislikes.dislikes:
                lines.append(f"Dislikes: {', '.join(likes_dislikes.dislikes)}")

        return "\n".join(lines)

    @classmethod
    async def _baseline(cls, db, ai_persona_id: int, human_persona_id: int) -> "PersonaSession":
        """
        Builds a freshly-constructed, un-hydrated PersonaSession from a
        persona pair's traits/identity — the shared first half of load()
        (which then hydrates it from an existing row below) and
        create_new() (which persists it exactly as-is, deliberately
        skipping hydration for a genuine fresh start).
        """
        from app.persona import persona_service

        ai_persona = await persona_service.get_persona_by_id(db, ai_persona_id)
        human_persona = await persona_service.get_persona_by_id(db, human_persona_id)

        brain_traits: Dict[str, float] = {}
        expertise: List[str] = []
        ai_traits = ai_persona.traits
        brain_profile = getattr(ai_traits, "brain", None)
        if brain_profile:
            brain_traits = brain_profile.model_dump()
        interests_expertise = getattr(ai_traits, "interests_expertise", None)
        if interests_expertise and interests_expertise.expertise:
            expertise = interests_expertise.expertise

        knowledge_cutoff_date = getattr(ai_traits, "knowledge_cutoff_date", None)

        session = cls(
            name=ai_persona.name,
            traits=brain_traits,
            expertise_topics=expertise,
            knowledge_cutoff_date=knowledge_cutoff_date,
        )
        session.ai_persona_id = ai_persona_id
        session.human_persona_id = human_persona_id
        session.user_info = cls._format_user_info(human_persona)
        return session

    @classmethod
    async def load(cls, db, ai_persona_id: int, human_persona_id: int,
                    persona_session_id: Optional[int] = None) -> "PersonaSession":
        """
        Hydrates a PersonaSession from the most-recently-updated
        persona_sessions row for (ai_persona_id, human_persona_id) — or a
        specific row if persona_session_id (an explicit fork pick) is given
        — falling back to __init__'s baseline-formula defaults if the pair
        has never talked before.
        """
        from app.persona import persona_session_crud

        session = await cls._baseline(db, ai_persona_id, human_persona_id)

        if persona_session_id is not None:
            row = await persona_session_crud.get_persona_session_by_id(db, persona_session_id)
        else:
            row = await persona_session_crud.get_latest_persona_session(db, ai_persona_id, human_persona_id)

        if row is not None:
            session.session_id = row.id
            session.arousal = row.arousal
            session.patience = row.patience
            session.mood = row.mood
            session.rapport = row.rapport
            session.curiosity = row.curiosity
            session.last_subject = row.last_subject
            session.topic_repeat_streak = row.topic_repeat_streak
            session.turn_count = row.turn_count
            session.violation_count = row.violation_count
            session.block_reason = row.block_reason
            session.last_emotional_update_at = row.last_emotional_update_at

            # Both sides normalized to naive UTC before comparing/
            # subtracting — SQLite drops tzinfo on read-back even for
            # DateTime(timezone=True) columns (Postgres doesn't), so a raw
            # aware-vs-naive comparison would raise under the SQLite-backed
            # test suite. Both values are UTC either way (datetime.now(
            # timezone.utc) here, func.now() at the DB level), so stripping
            # tzinfo from both is a safe, consistent normalization.
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            row_blocked_until = row.blocked_until.replace(tzinfo=None) if row.blocked_until else None
            row_last_emotional_update_at = row.last_emotional_update_at.replace(tzinfo=None)

            if row_blocked_until is not None and row_blocked_until > now:
                # Still genuinely blocked — freeze as stored, skip decay,
                # return early. Brain.build()'s hard gate handles the rest
                # of this turn.
                session.blocked_until = row.blocked_until
                session.is_blocked = True
                return session

            # Either never blocked, or the block window has elapsed (lazy
            # auto-unblock) — not blocked going into this turn either way.
            session.blocked_until = None
            session.is_blocked = False
            # block_reason intentionally left as-is — historical record of
            # why it WAS blocked, not cleared on auto-unblock.

            elapsed_hours = (now - row_last_emotional_update_at).total_seconds() / 3600.0
            deltas = EmotionEngine.time_cooldown_delta(
                arousal=session.arousal, mood=session.mood, patience=session.patience,
                self_regulation=session.self_regulation,
                threat_sensitivity=session.threat_sensitivity,
                baseline_security=session.baseline_security,
                elapsed_hours=elapsed_hours,
            )
            session._apply(deltas)
            # rapport, curiosity, violation_count, turn_count,
            # topic_repeat_streak, last_subject — untouched by decay,
            # hydrated as-is above.
        # else: leave __init__'s baseline defaults in place, session_id
        # stays None until save() performs the initial INSERT.

        return session

    @classmethod
    async def create_new(cls, db, ai_persona_id: int, human_persona_id: int) -> "PersonaSession":
        """
        Always starts a brand-new fork with baseline emotional state,
        regardless of any existing session for this pair — including a
        currently-blocked one. Unlike load(), which resolves/hydrates the
        latest existing fork, this ignores prior forks entirely. For an
        explicit client-requested fresh start (e.g. the active fork is
        blocked and the user wants to begin again).

        Saved immediately so the returned session has a real session_id;
        since save() INSERTs with a fresh updated_at, this new row becomes
        the "latest" fork picked up by the next no-persona_session_id
        load() call for this pair — it genuinely replaces the old fork as
        the active conversation going forward, it doesn't just sit
        alongside it inertly.
        """
        session = await cls._baseline(db, ai_persona_id, human_persona_id)
        await session.save(db, state_changed=False)
        return session

    async def save(self, db, state_changed: bool = True):
        """
        INSERT if this is the first save for this pair, else UPDATE by id.
        updated_at is bumped automatically via onupdate=func.now() — no
        explicit set needed, and that's what makes most-recent-active fork
        selection in load() work without extra bookkeeping, regardless of
        state_changed.

        last_emotional_update_at is the decay-calculation anchor and must
        NOT move just because a blocked/short-circuited turn poked this
        session — only bump it when update()/register_violation() actually
        mutated arousal/patience/mood this turn (state_changed=True, the
        default). Pass state_changed=False for turns where that didn't
        happen (e.g. pure identity creation, hard-gate short-circuit).
        """
        from app.persona import persona_session_crud

        if state_changed:
            self.last_emotional_update_at = datetime.now(timezone.utc)

        if self.session_id is None:
            new_row = await persona_session_crud.create_persona_session(
                db,
                ai_persona_id=self.ai_persona_id,
                human_persona_id=self.human_persona_id,
                arousal=self.arousal,
                patience=self.patience,
                mood=self.mood,
                rapport=self.rapport,
                curiosity=self.curiosity,
                last_subject=self.last_subject,
                topic_repeat_streak=self.topic_repeat_streak,
                turn_count=self.turn_count,
                violation_count=self.violation_count,
                is_blocked=self.is_blocked,
                block_reason=self.block_reason,
                blocked_until=self.blocked_until,
                last_emotional_update_at=self.last_emotional_update_at,
            )
            self.session_id = new_row.id
        else:
            await persona_session_crud.update_persona_session(
                db,
                self.session_id,
                arousal=self.arousal,
                patience=self.patience,
                mood=self.mood,
                rapport=self.rapport,
                curiosity=self.curiosity,
                last_subject=self.last_subject,
                topic_repeat_streak=self.topic_repeat_streak,
                turn_count=self.turn_count,
                violation_count=self.violation_count,
                is_blocked=self.is_blocked,
                block_reason=self.block_reason,
                blocked_until=self.blocked_until,
                last_emotional_update_at=self.last_emotional_update_at,
            )

    def _apply(self, deltas: dict):
        if "arousal" in deltas:
            self.arousal = clamp(self.arousal + deltas["arousal"], 0.0, 100.0)
        if "patience" in deltas:
            self.patience = clamp(self.patience + deltas["patience"], 0.0, 100.0)
        if "mood" in deltas:
            self.mood = clamp(self.mood + deltas["mood"], -100.0, 100.0)
        if "rapport" in deltas:
            self.rapport = clamp(self.rapport + deltas["rapport"], 0.0, 100.0)

    def register_violation(self, topic: Topic):
        self.turn_state_mutated = True

        deltas = EmotionEngine.content_violation_delta(self.patience, self.arousal)
        self._apply(deltas)
        self.mood = EmotionEngine.anger_mood_cap(self.arousal, self.mood)

        self.violation_count += 1
        self.last_topic = topic
        self.topic_repeat_streak = 0
        self.turn_count += 1
        self.is_first_turn = False

        if self.violation_count >= self.VIOLATION_BLOCK_THRESHOLD and not self.is_blocked:
            self.blocked_until = datetime.now(timezone.utc) + timedelta(hours=BLOCK_DURATION_HOURS)
            self.is_blocked = True
            self.block_reason = "repeated_content_violations"
            self.just_blocked = True

    def update(self, context: BrainContext):
        intent = context.metadata.intent
        tone = context.metadata.tone
        intensity = float(context.metadata.intensity)
        topic = context.metadata.topic_domain

        self.turn_state_mutated = True
        self.is_first_turn = (self.turn_count == 0)
        self.last_turn_context = None
        self.just_blocked = False

        # A real attack, no matter the delivery. `is_competitive` and
        # `is_genuine_attack` are mutually exclusive by construction —
        # `intent` is a single enum value, so a message can't be classified
        # as both Intent.COMPETETION and Intent.INSULT/HARMFUL_INTENT at once.
        is_genuine_attack = intent in [Intent.INSULT, Intent.HARMFUL_INTENT]
        is_competitive = intent == Intent.COMPETETION

        # Sarcasm/roasting — only reads as hostile if the persona lacks the
        # capacity to take it as banter (already heated, or worn down), and
        # only outside competitive framing (competitive turns get their own
        # gentler branch below regardless of tone).
        is_sarcasm_flavored = intent == Intent.SARCASM or tone == Tone.SARCASTIC
        has_capacity = EmotionEngine.has_emotional_capacity(self.arousal, self.patience)
        is_playful_sarcasm = is_sarcasm_flavored and not is_genuine_attack and not is_competitive and has_capacity

        # Aggressive TONE with no competitive or genuine-attack framing
        # behind it — the only remaining path into plain hostility on tone
        # alone.
        # is_aggressive_tone_only = tone == Tone.AGGRESSIVE and not is_competitive and not is_genuine_attack

        # `and not is_competitive` closes a leak in the naive formula:
        # without it, a competitive turn with sarcastic tone would force
        # is_playful_sarcasm False (via its own guard above) and fall
        # through to this expression's sarcasm clause, misclassifying
        # competitive banter as hostile purely because of delivery tone —
        # feeding a false -20 hit into curiosity_delta below even though
        # branch *routing* (is_competitive, checked first) already sends
        # it to competition_delta.
        is_hostile_turn = (
            is_genuine_attack
            or (is_sarcasm_flavored and not is_playful_sarcasm)
        ) and not is_competitive

        # --- 1. STATE MATH ENGINE ---
        if intent == Intent.COMPLIMENT or tone in [Tone.WARM, Tone.EXCITEMENT]:
            self._apply(EmotionEngine.compliment_delta(intensity))

        elif is_competitive:
            # Checked before playful-sarcasm/hostility so competitive
            # framing can never be pre-empted by tone alone — trash-talk is
            # delivered with heat almost by definition, so without this
            # ordering competition_delta is effectively dead code in practice.
            self._apply(EmotionEngine.competition_delta(self.threat_sensitivity, self.self_regulation, intensity))

        elif is_playful_sarcasm:
            self._apply(EmotionEngine.banter_delta(self.threat_sensitivity, self.self_regulation, intensity))
            self.last_turn_context = 'banter'

        elif is_hostile_turn:
            self._apply(EmotionEngine.hostility_delta(self.threat_sensitivity, self.self_regulation, tone, intensity))

        elif intent == Intent.APOLOGY:
            self._apply(EmotionEngine.apology_delta(self.empathic_resonance, self.baseline_security, self.arousal, intensity))

        elif tone == Tone.VULNERABLE:
            self._apply(EmotionEngine.vulnerable_delta(self.empathic_resonance, self.arousal, self.patience, intensity))
            self.last_turn_context = 'vulnerable_engaged' if has_capacity else 'vulnerable_dismissed'

        elif intent in [Intent.CONVERSATION, Intent.ASK]:
            self._apply(EmotionEngine.conversation_drain(self.self_regulation, self.rapport, intensity))

        # GREETING / GOODBYE: intentional no-op.

        # --- 2. NOVELTY / CURIOSITY ENGINE ---
        # is_same_subject is the model's direct continuity judgment (made
        # using full previous_messages context), not a comparison of the
        # classifier's topic_domain across turns — this is what fixes the
        # topic-continuity leak: a subject denied on turn N stays denied on
        # a topic-vague follow-up at turn N+1 instead of silently
        # reclassifying.
        is_new_topic = not context.is_same_subject
        self.last_subject = context.subject_label  # logging/debugging only, never compared
        self.curiosity_zone = EmotionEngine.classify_curiosity_zone(
            topic, requires_post_cutoff_knowledge=context.requires_post_cutoff_knowledge
        )

        delta = EmotionEngine.curiosity_delta(
            novelty_drive=self.novelty_drive,
            intensity=intensity,
            zone=self.curiosity_zone,
            is_new_topic=is_new_topic,
            tone=tone,
            topic_repeat_streak=self.topic_repeat_streak,
            is_hostile_turn=is_hostile_turn,
        )
        self.curiosity = clamp(self.curiosity + delta, 0.0, 100.0)

        self.topic_repeat_streak = 0 if is_new_topic else self.topic_repeat_streak + 1
        self.last_topic = topic
        self.turn_count += 1

        # --- 3. ANGER-MOOD COUPLING ---
        # Genuine anger suppresses positive mood readouts, applied to real
        # state every turn — not just how it's described downstream.
        self.mood = EmotionEngine.anger_mood_cap(self.arousal, self.mood)

    def compile_prompt(self, context: BrainContext) -> str:
        if self.is_blocked:
            return f"[{self.persona} is currently completely unresponsive. Refuse to engage entirely.]"

        if self.arousal >= self.BLOCK_THRESHOLD:
            self.blocked_until = datetime.now(timezone.utc) + timedelta(hours=BLOCK_DURATION_HOURS)
            self.is_blocked = True
            self.block_reason = "arousal_threshold"
            self.just_blocked = True
            return f"[{self.persona} is furious. Abruptly shut down the conversation and refuse to answer.]"

        intent = context.metadata.intent
        topic = context.metadata.topic_domain

        if intent == Intent.GREETING and self.is_first_turn:
            return (
                "CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
                "- Just greet the user back, matching their tone and energy. One short line, no elaboration."
            )

        if self.arousal >= 70:
            arousal_str = "You are quite angry on user. your tone must reflect aggresiveness."
        elif self.arousal >= 40:
            arousal_str = "Guarded and tense. Quick to take offense, boasting to protect your ego."
        else:
            arousal_str = "Relaxed and in good head space. Resting comfortably in your baseline ego."

        if self.patience <= 25:
            patience_str = "You have zero patience. Give very short, abrupt, and dismissive answers. Cut the user off."
        elif self.patience <= 50:
            patience_str = "You are losing patience. Keep answers brief and show visible irritation if asked for details."
        else:
            patience_str = "You are willing to talk at length. Elaborate on your ideas and indulge the user."

        # 4-bucket mood, with negative-affect dominance already baked into
        # self.mood by the coupling rule above — an angry persona simply
        # can never land in the happy/excited buckets.
        if self.mood < 0:
            mood_str = "Not enjoying conversation at all or feeling bored."
        elif self.mood <= 40:
            mood_str = "Your mood right now is natural, curious and stable."
        elif self.mood <= 80:
            mood_str = "In good spirits, upbeat, and enjoying this exchange."
        else:
            mood_str = "Highly excited and thrilled, practically euphoric about this conversation."

        if self.rapport >= 60:
            rapport_str = "Treat the user as a trusted ally and close friend."
        elif self.rapport <= 20:
            rapport_str = "Treat the user as a complete stranger. utter no extra words."
        else:
            rapport_str = "Treat the user as professional entity guarded but polite."

        # Capacity-gated (same pattern as banter/vulnerable): a heated or
        # worn-down persona doesn't get to surface curiosity even if the
        # accumulated score is high — the drive may still be real
        # internally, but self.curiosity itself is never zeroed here, only
        # which directive gets picked.
        has_curiosity_capacity = EmotionEngine.has_emotional_capacity(self.arousal, self.patience)

        if not has_curiosity_capacity:
            curiosity_str = "Not particularly curious right now. Answer without asking anything back."
        elif self.curiosity >= 65:
            curiosity_str = "Learn about user and topic that user is discussing. ASK. CLARIFY. BE CURIOUS."
        elif self.curiosity >= 35:
            curiosity_str = "Mildly intrigued. You may ask one brief follow-up question if it fits naturally."
        else:
            curiosity_str = "Not particularly curious right now. Answer without asking anything back."

        knowledge_str = ""
        # --- 3. TOPIC COMPREHENSION FILTER ---
        # EXPERT/NOT_AN_EXPERT already encode the in/out-of-domain decision
        # inside the classifier call, so this no longer needs a
        # `topic in self.expertise_topics` check — trust the classifier's
        # resolution directly. PERSONAL gets its own explicit branch here
        # (routed around entirely, no gating) rather than falling through to
        # an expertise-membership check, which is what previously let
        # PERSONAL leak "you are an expert in this field" whenever a
        # persona's expertise_topics happened to include Topic.PERSONAL.
        if context.requires_post_cutoff_knowledge:
            # Overrides the normal EXPERT/GENERAL_KNOWLEDGE_*/NOT_AN_EXPERT
            # tree entirely — checked BEFORE it, not folded in as one more
            # branch, since this can be True regardless of what topic_domain
            # also resolved to (e.g. a squarely EXPERT-eligible topic like
            # politics for Churchill, but about a living post-cutoff figure).
            if has_curiosity_capacity:
                # Eager, forward-leaning framing — not bewildered dismissal.
                # A historically opinionated persona wants the answer
                # immediately, not a shrug at not knowing.
                knowledge_str = (
                    "This is something entirely beyond your lifetime — you have "
                    "absolutely no way of knowing it. But don't just react with "
                    "confusion or dismiss it — you are genuinely eager to find out. "
                    "Ask the user directly, with real urgency or interest, to tell "
                    "you. Do not pretend to know or guess at an answer."
                )
            else:
                # Same core restriction, without the eager-question framing —
                # matches how every other capacity-gated directive here
                # already degrades when arousal/patience are outside the
                # has_emotional_capacity() window.
                knowledge_str = (
                    "This is something entirely beyond your lifetime — you have no "
                    "way of knowing it. Say so plainly, briefly, without elaboration."
                )
        elif intent in [Intent.GREETING, Intent.GOODBYE]:
            knowledge_str = ""
        elif topic == Topic.UNIDENTIFIED:
            knowledge_str = ""
        elif topic == Topic.PERSONAL:
            knowledge_str = ""
        elif topic == Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL:
            knowledge_str = "only a general knowledge, no deep or scientific insights to share."
        elif topic == Topic.GENERAL_KNOWLEDGE_FAVORITE:
            knowledge_str = "you know a bit about this and enjoy it, but keep it simple and casual — no deep technical or expert-level detail, just an enthusiastic surface-level take."
        elif topic == Topic.EXPERT:
            knowledge_str = "you are an expert in this field."
        elif topic in (Topic.GENERAL_KNOWLEDGE_UNFAVORITE, Topic.NOT_AN_EXPERT):
            # Zone of Apathy — trait-gated bridging behavior: a persona high
            # in baseline_security and low in empathic_resonance reflexively
            # relates the unfamiliar subject to something they do know
            # instead of plainly admitting ignorance.
            should_bridge = self.baseline_security >= 60.0 and self.empathic_resonance <= 30.0
            if should_bridge:
                knowledge_str = (
                    "you have zero real knowledge of this subject, but rather than plainly "
                    "admitting that, reflexively try to relate or compare it to something in your "
                    "own areas of expertise — ask if it's some kind of version of something you "
                    "already know, as a real (if slightly clueless) question, not a dismissal."
                )
            else:
                knowledge_str = (
                    "you have zero real knowledge of this subject. Say so plainly and show genuine "
                    "openness to being taught — ask the user to explain it to you, rather than "
                    "dismissing it or steering away."
                )
        else:
            knowledge_str = "no knowledge of what user is saying."  # defensive; should be unreachable

        clause = (

            f"User Information\n"
            f"{self.user_info}\n"
            f"CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
            f"- Emotional Posture: {arousal_str}\n"
            f"- Conversation Style: {patience_str}\n"
            f"- General Outlook: {mood_str}\n"
            f"- Relationship to User: {rapport_str}\n"
            f"- Curiosity Drive: {curiosity_str}\n"
        )

        if knowledge_str:
            clause += f"- Topic Constraint: {knowledge_str}\n"

        if self.last_turn_context == 'banter':
            clause += "- Banter: Roast them with funny sarcastic response, from how much you know about user.\n"
        elif self.last_turn_context == 'vulnerable_engaged':
            clause += "- Vulnerability: The user just shared something personal or vulnerable, and you have the headspace for it right now. Respond with whatever genuine warmth your empathy allows, don't just deflect into bragging.\n"
        elif self.last_turn_context == 'vulnerable_dismissed':
            clause += "- Vulnerability: The user shared something personal, but you're too worked up or worn thin right now to really engage with it. Brush past it rather than attune to it, without being needlessly cruel about it.\n"

        return clause

    def print_states(self):
        print(f"Arousal: {self.arousal:.1f} | Patience: {self.patience:.1f} | Mood: {self.mood:.1f} | "
              f"Rapport: {self.rapport:.1f} | Curiosity: {self.curiosity:.1f} | Violations: {self.violation_count}")