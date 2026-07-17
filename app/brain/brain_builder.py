from .message_analysis import MessageAnalysis

from app.persona.persona_session import PersonaSession

from .brain_component import BrainComponent
from .context import BrainContext
from .response_style import ResponseStyle


class Brain:


    def __init__(self, components: list[BrainComponent]):
        self.global_components = components

    async def build(
        self,
        question: str,
        persona_session: PersonaSession,
    ) -> str:

        # 1. Analyze the incoming message
        metadata = await MessageAnalysis.analyze(question)

        context = BrainContext(
            question=question,
            metadata=metadata,
        )

        # 2. Language check
        if context.metadata.language not in ["english", "en"]:
            return (
                f"Refuse to answer in a {persona_session.persona} manner, "
                "because you do not understand languages other than English."
            )

        print(
            "Parsed Message Metadata:\n",
            metadata.model_dump_json(indent=2),
        )

        # 3. Register all brain components
        all_components: list[BrainComponent] = [
            persona_session,
            *self.global_components,
        ]

        # 4. Update internal state
        for component in all_components:
            component.update(context)

        # 5. Compile prompt fragments
        prompt_sections = [
            f"You are adopting the persona of {persona_session.persona}."
        ]

        for component in all_components:
            prompt_sections.append(
                component.compile_prompt(context)
            )

        # 6. Build final prompt
        return "\n\n".join(prompt_sections)
    


brain : Brain = Brain([
        ResponseStyle()
    ])