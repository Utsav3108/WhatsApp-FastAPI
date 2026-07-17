
from .schemas import UserMessageMetaDataResponse

from classifiers.language_classifiers import predict

class MessageAnalysis():

    # Extract Complete Meta Classification Bundle via single Gemini 2.5 call
    @staticmethod
    async def _generate_message_metadata(text: str) -> UserMessageMetaDataResponse:
        """
        Sends text to the model and returns a clean metadata object 
        containing validated Intent, Tone, Intensity, and TopicDomain.
        """
        system_prompt = (
            "You are an affective NLP parsing engine. Analyze the incoming user statement and "
            "extract the primary structural intent, emotional tone, numeric intensity score, and topic domain.\n\n"
            "INTENSITY SCALING MATRIX:\n"
            "- 1-20: Mild, factual, or polite standard interactions.\n"
            "- 21-50: Moderate emotional variance (clear annoyance, distinct preference, or active eagerness).\n"
            "- 51-80: High emotional expression (use of exclamation marks, intense phrasing, or overt hostility).\n"
            "- 81-100: Extreme or unhinged reactions (absolute rage, intense panic, or euphoric praise)."
        )

        from app.gemini import client

        response = await client.aio.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=text,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_schema": UserMessageMetaDataResponse, 
                "temperature": 0.1  # Locked temperature down for stable deterministic parsing
            }
        )
        
        # Instantiate the pydantic model directly from the validated JSON payload
        return UserMessageMetaDataResponse.model_validate_json(response.text)



    @staticmethod
    def _detect_language(text: str) -> str:
        """
        Returns the language with the highest confidence score.
        """

        result: dict[str, float] = predict(text)

        return max(result, key=result.get)

    @staticmethod
    async def analyze(text: str) -> UserMessageMetaDataResponse:
        metadata : UserMessageMetaDataResponse = await MessageAnalysis._generate_message_metadata(text)

        metadata.language = MessageAnalysis._detect_language(text)

        return metadata