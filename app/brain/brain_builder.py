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

    async def build(
        self,
        question: str,
        persona_session: PersonaSession,
    ) -> str:

        # 1. Analyze the incoming message
        metadata = await MessageAnalysis.analyze(
            previous_message_summary=persona_session.summary, 
            text=question
            )

        print(
            "Parsed Message Metadata:\n",
            metadata.model_dump_json(indent=2),
        )

        if metadata.topic_domain in self.harmful_topics:
            return """  
            
            Threaten to block the user or take a legal action staying in charector." \
            Response length must be under 4 sentences.        

            """
        
        if metadata.topic_domain in self.sexual_topics:
            return """  
            
            Order or warn them maintain the decoram, and talk about things worth talking about!
            Response length must be under 4 sentences.        

            """


        context = BrainContext(
            question=question,
            metadata=metadata,
        )

        # 2. Language check
        if context.metadata.language.lower() not in ["english", "en"]:
            return (
                f" In {persona_session.persona} manner refuse to answer, "
                "ask user to only speak in english."
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