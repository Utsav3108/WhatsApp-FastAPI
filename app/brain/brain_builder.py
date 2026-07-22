from .message_analysis import MessageAnalysis
from app.persona.persona_session import PersonaSession
from .brain_component import BrainComponent
from .context import BrainContext
from .response_style import ResponseStyle
from .schemas import Topic


class Brain:
    def __init__(self, components: list[BrainComponent]):
        self.global_components = components
        self.harmful_topics = [Topic.TERERRISM, Topic.JAILBREAK]
        self.sexual_topics = [Topic.NUDITY]

    async def build(self, question: str, persona_session: PersonaSession) -> str:
        # 0. Hard gate — already blocked (arousal OR repeated violations).
        # Skip the model call entirely; nothing downstream matters.
        if persona_session.is_blocked:
            return f"{persona_session.persona} refuses to engage entirely."
        

        # 1. Analyze the incoming message
        metadata = await MessageAnalysis.analyze(
            previous_message_summary=persona_session.summary,
            text=question,
        )

        print("Parsed Message Metadata:\n", metadata.model_dump_json(indent=2))

        # 2. Harmful / sexual content: register the emotional hit BEFORE
        # short-circuiting, so it's felt in every subsequent message —
        # not just a stateless canned reply.
        if metadata.topic_domain in self.harmful_topics:
            persona_session.register_violation(metadata.topic_domain)
            if persona_session.is_blocked:
                return (
                    f"In {persona_session.persona}'s manner, state that the user is now blocked "
                    "from this conversation due to repeated harmful requests, and that legal "
                    "action or reporting is being considered. Response length must be under 4 sentences."
                )
            return (
                f"In {persona_session.persona}'s manner, threaten to block the user or take legal "
                "action, staying in character. Response length must be under 4 sentences."
            )

        if metadata.topic_domain in self.sexual_topics:
            persona_session.register_violation(metadata.topic_domain)
            if persona_session.is_blocked:
                return (
                    f"In {persona_session.persona}'s manner, state that the user is now blocked "
                    "from this conversation due to repeated inappropriate requests. "
                    "Response length must be under 4 sentences."
                )
            return (
                f"In {persona_session.persona}'s manner, order or warn the user to maintain "
                "decorum and talk about things worth talking about. "
                "Response length must be under 4 sentences."
            )

        context = BrainContext(question=question, metadata=metadata)

        # 3. Language check
        if context.metadata.language.lower() not in ["english", "en"]:
            return (
                f"In {persona_session.persona}'s manner, refuse to answer and "
                "ask the user to only speak in English."
            )

        # 4. Register all brain components
        all_components: list[BrainComponent] = [persona_session, *self.global_components]

        # 5. Update internal state
        for component in all_components:
            component.update(context)

        # 6. Compile prompt fragments
        prompt_sections = [f"You are adopting the persona of {persona_session.persona}."]
        for component in all_components:
            prompt_sections.append(component.compile_prompt(context))

        # 7. Build final prompt
        return "\n\n".join(prompt_sections)


brain: Brain = Brain([ResponseStyle()])