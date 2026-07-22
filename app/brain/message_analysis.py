from typing import List
from .schemas import UserMessageMetaDataResponse, Topic

from classifiers.language_classifiers import predict

class MessageAnalysis():

    # Extract Complete Meta Classification Bundle via single Gemini 2.5 call
    @staticmethod
    async def _generate_message_metadata(previous_messages, text: str, expertise_topics: List[Topic]) -> UserMessageMetaDataResponse:
        """
        Sends text to the model and returns a clean metadata object
        containing validated Intent, Tone, Intensity, and TopicDomain.
        """
        # Exclude the GK meta-buckets themselves — they're fallback
        # classifications, not real subject domains, so listing them as
        # "favorites" would confuse the disambiguation rather than help it.
        gk_meta_topics = {
            Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL,
            Topic.GENERAL_KNOWLEDGE_FAVORITE,
            Topic.GENERAL_KNOWLEDGE_UNFAVORITE,
        }
        real_domains = [t.value for t in expertise_topics if t not in gk_meta_topics]
        domains_list = ", ".join(real_domains) if real_domains else "(none specified)"

        system_prompt = (
            "You are an affective NLP parsing engine. Analyze the incoming user statement and "
            "extract the language, primary structural intent, emotional tone, numeric intensity score, and topic domain.\n\n"
            "ONLY Gibberish ex: 'wrnwerjkwrkjbjrwe' will be labeled as UNIDENTIFIED Topic."
            "# PREVIOUS MESSAGES"
            f"{previous_messages}\n"
            "INTENSITY SCALING MATRIX:\n"
            "- 1-20: Mild, factual, or polite standard interactions.\n"
            "- 21-50: Moderate emotional variance (clear annoyance, distinct preference, or active eagerness).\n"
            "- 51-80: High emotional expression (use of exclamation marks, intense phrasing, or overt hostility).\n"
            "- 81-100: Extreme or unhinged reactions (absolute rage, intense panic, or euphoric praise).\n\n"
            "TOPIC DISAMBIGUATION FOR GENERAL-KNOWLEDGE-STYLE QUESTIONS:\n"
            "This persona is professionally knowledgeable ONLY in these domains: "
            f"{domains_list}.\n\n"
            "When the user asks a casual, general-knowledge-style question — NOT a substantive or "
            "technical request within one of the domains above — choose between these three GK topics:\n"
            "- GeneralKnowledgeLifeOrPersonal: about the persona's own life, upbringing, journey, "
            "relationships, or opinions.\n"
            "- GeneralKnowledgeFavorite: casually touches one of the persona's professional domains "
            f"listed above ({domains_list}), phrased lightly rather than technically.\n"
            "- GeneralKnowledgeUnfavorite: a light, general-knowledge-style question about ANY subject "
            "NOT in the domain list above and not about the persona's personal life — including subjects "
            "like science, biology, or other academic topics the persona has no professional grounding in, "
            "even if the question itself sounds simple or trivia-like (e.g. 'explain mitochondria').\n\n"
            "If the question is a substantive, in-depth technical request squarely within one of the "
            "domains above, classify it under that domain topic directly rather than a GK bucket.\n"
            "LABEL TOPIC BY STRCITLY REVIEWING # PREVIOUS MESSAGE"
        )
        print("Message analysis prompt: ", system_prompt)
        from app.gemini import client
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=text,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": UserMessageMetaDataResponse,
                "temperature": 0.1
            }
        )

        return UserMessageMetaDataResponse.model_validate_json(response.text)
    @staticmethod
    def _detect_language(text: str) -> str:
        """
        Returns the language with the highest confidence score.
        """

        result: dict[str, float] = predict(text)

        return max(result, key=result.get)

    @staticmethod
    async def analyze(previous_messages, text: str, expertise_topics: List[Topic]) -> UserMessageMetaDataResponse:
        metadata : UserMessageMetaDataResponse = await MessageAnalysis._generate_message_metadata(
            previous_messages=previous_messages, 
            text=text,
            expertise_topics=expertise_topics
            )

        # metadata.language = MessageAnalysis._detect_language(text)

        return metadata