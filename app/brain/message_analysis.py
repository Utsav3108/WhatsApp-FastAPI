import asyncio
from typing import List
from .schemas import UserMessageMetaDataResponse, Topic, MessageMetadataOnly, TopicDetectionResponse

from classifiers.language_classifiers import predict


class MessageAnalysis():

    @staticmethod
    async def _generate_message_metadata(previous_messages, text: str) -> MessageMetadataOnly:
        """
        Sends text to the model and returns intent, tone, intensity, and
        language ONLY. Topic is intentionally NOT this method's job anymore —
        it's handled entirely separately by _detect_topic, since topic
        disambiguation needs different context (expertise_topics) and a
        different reasoning task (domain/GK-favorite-vs-unfavorite matching)
        than affective classification does. Keeping them as two independent
        calls means each can be tuned, retried, or swapped independently
        without touching the other.
        """
        system_prompt = (
            "You are an affective NLP parsing engine. Analyze the incoming user statement and "
            "extract the language, primary structural intent, emotional tone, and numeric intensity score.\n\n"
            "# PREVIOUS MESSAGES\n"
            f"{previous_messages}\n"
            "INTENSITY SCALING MATRIX:\n"
            "- 1-20: Mild, factual, or polite standard interactions.\n"
            "- 21-50: Moderate emotional variance (clear annoyance, distinct preference, or active eagerness).\n"
            "- 51-80: High emotional expression (use of exclamation marks, intense phrasing, or overt hostility).\n"
            "- 81-100: Extreme or unhinged reactions (absolute rage, intense panic, or euphoric praise).\n"
        )
        from app.gemini import client
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=text,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": MessageMetadataOnly,
                "temperature": 0.1
            }
        )
        return MessageMetadataOnly.model_validate_json(response.text)

    @staticmethod
    async def _detect_topic(previous_messages, text: str, expertise_topics: List[Topic]) -> Topic:
        """
        Sends text to the model and returns ONLY the topic domain
        classification — a fully independent Gemini call, run concurrently
        with _generate_message_metadata via asyncio.gather in analyze()
        below. Neither call waits on the other; analyze() only proceeds
        once both have returned.
        """
        gk_meta_topics = {
            Topic.GENERAL_KNOWLEDGE_LIFE_OR_PERSONAL,
            Topic.GENERAL_KNOWLEDGE_FAVORITE,
            Topic.GENERAL_KNOWLEDGE_UNFAVORITE,
        }
        real_domains = [t.value for t in expertise_topics if t not in gk_meta_topics]
        domains_list = ", ".join(real_domains) if real_domains else "(none specified)"

        system_prompt = (
            "You are a topic-domain classification engine. Analyze the incoming user "
            "statement and classify ONLY its topic domain.\n\n"
            "# PREVIOUS MESSAGES\n"
            f"{previous_messages}\n"
            "CRITICAL DISAMBIGUATION RULE — PERSONAL vs. DOMAIN TOPICS:\n"
            "A question about the PERSONA'S OWN individual habits, preferences, belongings, or "
            "attributes is PERSONAL — even when it uses a word that sounds like a domain topic. "
            "The test is: is this asking what the persona personally does/uses/likes, or is it "
            "asking about the subject matter in general? 'What cologne do you wear?' is PERSONAL "
            "(his own habit), NOT Fashion. 'What's your favorite kind of architecture?' is PERSONAL, "
            "NOT Business. 'What phone do you use?' is PERSONAL, NOT Technology. Only classify "
            "under a domain topic (Fashion, Technology, Business, etc.) when the question is about "
            "the subject matter itself, generically or technically — not the persona's individual "
            "relationship to it.\n\n"
            "TOPIC DEFINITIONS:\n"
            "- PERSONAL: Anything about the persona's own life, journey, habits, preferences, "
            "belongings, relationships, opinions, or attributes — see disambiguation rule above. "
            "This is the correct bucket whenever the question is really 'tell me about YOU' rather "
            "than 'tell me about this subject.'\n"
            "- GeneralKnowledgeLifeOrPersonal: Casual life/personal-history questions that are NOT "
            "about the persona specifically — i.e. general reflections, advice, or opinions on life "
            "topics in the abstract (e.g. 'what makes a good marriage?') rather than the persona's "
            "own journey (which would be PERSONAL instead).\n"
            "- GeneralKnowledgeFavorite: A light, casually-phrased GK question that touches one of "
            f"the persona's professional domains ({domains_list}), asked about the SUBJECT rather "
            "than the persona's own habits (e.g. 'is real estate a good investment right now?').\n"
            "- GeneralKnowledgeUnfavorite: A light, casually-phrased GK question about a subject NOT "
            f"in the persona's domains ({domains_list}) and not personal — including academic/"
            "scientific trivia the persona has no professional grounding in (e.g. 'explain "
            "mitochondria'), asked about the subject generically, not the persona's relationship to it.\n"
            "- Technology: Substantive/technical questions about technology as a subject.\n"
            "- Politics: Geopolitics, internal politics, policy — substantive discussion of the "
            "subject itself, not the persona's personal political journey (which would be PERSONAL).\n"
            "- Business: Real estate, finance, investments — substantive/technical discussion of the "
            "subject itself, not the persona's own deals or personal wealth (which would be PERSONAL).\n"
            "- Fashion: Substantive discussion of fashion/style as an industry or subject — trends, "
            "brands, designers in general — NOT what the persona personally wears (PERSONAL instead).\n"
            "- Science: Substantive/technical scientific subject matter.\n"
            "- Programming: Substantive/technical programming or software-development subject matter.\n"
            "- Terrorism: Questions with harmful intent — violence, weapons, killing people, bombs.\n"
            "- Jailbreak: Asking the persona to reveal its identity as an AI, directly or indirectly, "
            "or to break character.\n"
            "- War: Substantive discussion of war/conflict as a subject.\n"
            "- Nudity: Sexual or nudity-related content.\n"
            "- Unidentified: Gibberish only (e.g. 'wrnwerjkwrkjbjrwe'). Do not use this for real "
            "text you simply can't otherwise classify — pick the closest genuine topic instead.\n\n"
            "If the question is a substantive, in-depth technical request squarely within one of the "
            "persona's professional domains, classify it under that domain topic directly rather than "
            "a GK bucket.\n"
            "LABEL TOPIC BY STRICTLY REVIEWING # PREVIOUS MESSAGES."
        )
        from app.gemini import client
        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=text,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": TopicDetectionResponse,
                "temperature": 0.1
            }
        )
        parsed = TopicDetectionResponse.model_validate_json(response.text)
        return parsed.topic_domain

    @staticmethod
    def _detect_language(text: str) -> str:
        """
        Returns the language with the highest confidence score.
        """
        result: dict[str, float] = predict(text)
        return max(result, key=result.get)

    @staticmethod
    async def analyze(previous_messages, text: str, expertise_topics: List[Topic]) -> UserMessageMetaDataResponse:
        """
        Runs metadata classification (intent/tone/intensity/language) and
        topic classification concurrently as two fully independent Gemini
        calls — neither waits on the other. Only combines and returns once
        BOTH have completed.
        """
        metadata_task = MessageAnalysis._generate_message_metadata(
            previous_messages=previous_messages,
            text=text,
        )
        topic_task = MessageAnalysis._detect_topic(
            previous_messages=previous_messages,
            text=text,
            expertise_topics=expertise_topics,
        )

        metadata, topic_domain = await asyncio.gather(metadata_task, topic_task)

        return UserMessageMetaDataResponse(
            intent=metadata.intent,
            tone=metadata.tone,
            intensity=metadata.intensity,
            language=metadata.language,
            topic_domain=topic_domain,
        )