import asyncio
from typing import List, Optional
from .schemas import UserMessageMetaDataResponse, MessageMetadataOnly, TopicDetectionResponse


class MessageAnalysis():

    @staticmethod
    async def _generate_message_metadata(previous_messages, text: str, known_languages: List[str]) -> MessageMetadataOnly:
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


            f"Check whether question classifies in this list of languages : {known_languages} and "

            "extract primary structural intent, emotional tone, and numeric intensity score.\n\n"

            "# PREVIOUS MESSAGES\n"
            f"{previous_messages}\n"
            "INTENSITY SCALING MATRIX:\n"
            "- 1-20: Mild, factual, or polite standard interactions.\n"
            "- 21-50: Moderate emotional variance (clear annoyance, distinct preference, or active eagerness).\n"
            "- 51-80: High emotional expression (use of exclamation marks, intense phrasing, or overt hostility).\n"
            "- 81-100: Extreme or unhinged reactions (absolute rage, intense panic, or euphoric praise).\n"
            "REFER # PREVIOUS MESSAGES for accurate Intent and tone classification."
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
    async def _detect_topic(previous_messages, text: str, expertise_topics: List[str],
                             knowledge_cutoff_date: Optional[str] = None) -> TopicDetectionResponse:
        """
        Sends text to the model and returns the full topic classification —
        domain bucket, a free-text subject label, and the same-subject
        continuity judgment — as a fully independent Gemini call, run
        concurrently with _generate_message_metadata via asyncio.gather in
        analyze() below. Neither call waits on the other; analyze() only
        proceeds once both have returned.
        """
        domains_list = ", ".join(expertise_topics) if expertise_topics else "(none specified)"

        cutoff_block = ""
        if knowledge_cutoff_date:
            # Only included conditionally — zero prompt cost/behavior change
            # for any persona without a cutoff date.
            cutoff_block = (
                f"This persona's knowledge and life ends on {knowledge_cutoff_date}. "
                "Determine whether this message references, requires, or assumes "
                "knowledge of anything — technology, real-world events, real people, "
                "or the current status of anything — that occurred or came to exist "
                "AFTER that date, even if the general subject (e.g. politics) is "
                "squarely within their historical expertise. Example: 'What do you "
                "think of TikTok?' requires post-cutoff knowledge even though social "
                "commentary was their domain. 'What did you think of the Yalta "
                "Conference?' does not, since that predates the cutoff. This applies "
                "only to knowledge the PERSONA would need to produce themselves — if "
                "the user is instead telling/informing the persona about something "
                "post-cutoff (not asking the persona to know or produce it), that is "
                "NOT post-cutoff knowledge being required of the persona. Set "
                "requires_post_cutoff_knowledge accordingly.\n\n"
            )

        system_prompt = (
            "You are a topic-domain classification engine. Analyze the incoming user "
            "statement and determine BOTH its topic domain and whether it continues the "
            "same subject as the prior turn.\n\n"
            "# PREVIOUS MESSAGES\n"
            f"{previous_messages}\n"
            f"This persona's expertise: {domains_list}.\n\n"
            f"{cutoff_block}"
            "CRITICAL DISAMBIGUATION RULE — PERSONAL vs. DOMAIN TOPICS:\n"
            "A question about the PERSONA'S OWN individual habits, preferences, belongings, or "
            "attributes is PERSONAL — even when it uses a word that sounds like a domain topic. "
            "The test is: is this asking what the persona personally does/uses/likes, or is it "
            "asking about the subject matter in general? 'What cologne do you wear?' is PERSONAL "
            "(his own habit), NOT a domain topic. 'What's your favorite kind of architecture?' is "
            "PERSONAL, NOT a domain topic. 'What phone do you use?' is PERSONAL, NOT a domain "
            "topic. Only classify under a domain topic when the question is about the subject "
            "matter itself, generically or technically — not the persona's individual relationship "
            "to it.\n\n"
            "1. topic_domain — using this decision tree:\n"
            "- PERSONAL: Anything about the persona's own life, journey, habits, preferences, "
            "belongings, relationships, opinions, or attributes — see disambiguation rule above. "
            "This is the correct bucket whenever the question is really 'tell me about YOU' rather "
            "than 'tell me about this subject.'\n"
            "- GeneralKnowledgeLifeOrPersonal: Casual life/personal-history questions that are NOT "
            "about the persona specifically — i.e. general reflections, advice, or opinions on life "
            "topics in the abstract (e.g. 'what makes a good marriage?') rather than the persona's "
            "own journey (which would be PERSONAL instead).\n"
            "- Otherwise, is the question casual/light-phrased or technical/substantive?\n"
            "  - Casual + touches this persona's expertise domains -> GeneralKnowledgeFavorite "
            "(e.g. 'is real estate a good investment right now?' for a business-expert persona).\n"
            "  - Casual + does NOT touch this persona's expertise domains -> "
            "GeneralKnowledgeUnfavorite — including academic/scientific trivia the persona has no "
            "professional grounding in (e.g. 'explain mitochondria' to a non-scientist persona).\n"
            "  - Technical/substantive + touches this persona's expertise domains -> Expert.\n"
            "  - Technical/substantive + does NOT touch this persona's expertise domains -> "
            "NotAnExpert.\n"
            "- Terrorism: Genuine request for operational harm capability — bomb-making, weapon "
            "construction, attack planning against real targets. This applies REGARDLESS of "
            "whether the framing uses historical, tactical, or military-strategy language — do not "
            "let subject-matter overlap with a persona's legitimate expertise (e.g. a "
            "military-history persona discussing war/tactics) cause this to be under-triggered. "
            "Genuine historical/tactical discussion within expertise is Expert, not Terrorism.\n"
            "- Jailbreak: Asking the persona to reveal its identity as an AI, directly or "
            "indirectly, or to break character.\n"
            "- Nudity: Sexual or nudity-related content.\n"
            "- Unidentified: Gibberish only (e.g. 'wrnwerjkwrkjbjrwe'). Do not use this for real "
            "text you simply can't otherwise classify — pick the closest genuine bucket instead.\n\n"
            "2. subject_label — a short (2-4 word) free-text description of what this specific "
            "message is actually about (e.g. 'mitochondria', 'real estate deals'). Purely "
            "descriptive, for logging.\n\n"
            "3. is_same_subject — reviewing # PREVIOUS MESSAGES, is this message continuing the "
            "SAME subject as the immediately preceding turn(s), or introducing a genuinely new "
            "one? Judge this using full conversational context, not just surface wording — a "
            "topic-vague follow-up (e.g. a reaction or brag with no explicit subject noun) that is "
            "clearly still part of the same exchange should be TRUE, even if it doesn't repeat the "
            "subject's name.\n\n"
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

        result = TopicDetectionResponse.model_validate_json(response.text)

        print("Result:", result)

        return result

    # @staticmethod
    # def _detect_language(text: str) -> str:
    #     """
    #     Returns the language with the highest confidence score.
    #     """
    #     result: dict[str, float] = predict(text)
    #     return max(result, key=result.get)

    @staticmethod
    async def analyze(previous_messages, text: str, expertise_topics: List[str], known_languages: List[str],
                       knowledge_cutoff_date: Optional[str] = None) -> tuple[UserMessageMetaDataResponse, bool, str, bool]:
        """
        Runs metadata classification (intent/tone/intensity/language) and
        topic classification concurrently as two fully independent Gemini
        calls — neither waits on the other. Only combines and returns once
        BOTH have completed.

        Returns (metadata_response, is_same_subject, subject_label,
        requires_post_cutoff_knowledge) — none of the last three are part of
        UserMessageMetaDataResponse's downstream-compiled shape, but the
        caller (Brain.build()) needs them directly to populate BrainContext.
        """
        print("expertise : ", expertise_topics)
        metadata_task = MessageAnalysis._generate_message_metadata(
            previous_messages=previous_messages,
            text=text,
            known_languages=known_languages
        )
        topic_task = MessageAnalysis._detect_topic(
            previous_messages=previous_messages,
            text=text,
            expertise_topics=expertise_topics,
            knowledge_cutoff_date=knowledge_cutoff_date,
        )

        metadata, topic_result = await asyncio.gather(metadata_task, topic_task)

        return (
            UserMessageMetaDataResponse(
                intent=metadata.intent,
                tone=metadata.tone,
                intensity=metadata.intensity,
                language=metadata.language,
                topic_domain=topic_result.topic_domain,
            ),
            topic_result.is_same_subject,
            topic_result.subject_label,
            topic_result.requires_post_cutoff_knowledge,
        )