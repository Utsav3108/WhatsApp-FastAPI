
from google import genai
from google.genai import types
import time
import asyncio
from google.genai.errors import ServerError, APIError 
import os
import dotenv


from typing import List, Union
import json
from app import models
from app import schemas

from app.enums import Intent, Tone, TopicDomain, UserMessageMetaDataResponse
from typing import Dict, List, Any

dotenv.load_dotenv()  # Load environment variables from .env file

from classifiers.preprocess import normalize_text
from classifiers.language_classifiers import predict
from classifiers.intent_classifier import predict as predict_intent


API_KEY = dotenv.get_key(dotenv.find_dotenv(), "GEMINI_API_KEY")

model = dotenv.get_key(dotenv.find_dotenv(), "GEMINI_MODEL")

client = genai.Client(api_key=API_KEY)

from pydantic import BaseModel

# Define the schema for the model to follow
import json

async def generate_message_metadata(text: str) -> UserMessageMetaDataResponse:
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



def understands_this_language(persona_languages : List[str], text: str) -> bool:

    """
    Analyzes the language of the given text using the language classifier model
    return only true or false. true means persona can understand the text, 
    false means persona cannot understand the text.
    """

    result = predict(text)

    for result_lang, prob in result.items():
        if result_lang in persona_languages and prob > 0.5:
            return True


    return False


def detect_intent(text: str) -> dict:
    """
    Analyzes the intent of the given text using the intent classifier model
    return a dictionary of intents and their probabilities.
    """

    result = predict_intent(text)

    return result

# Assuming understands_this_language and detect_intent are defined above

class Persona:
    def __init__(self, name: str, traits: Dict[str, float]):
        self.name = name
        
        # 1. Constant Traits
        self.threat_sensitivity = traits.get('threat_sensitivity', 50.0)
        self.self_regulation = traits.get('self_regulation', 50.0)
        self.novelty_drive = traits.get('novelty_drive', 50.0)
        self.baseline_security = traits.get('baseline_security', 50.0)
        self.empathic_resonance = traits.get('empathic_resonance', 50.0)
        
        # 2. Computed State
        self.arousal = max(0.0, 30.0 - (self.baseline_security / 4.0))
        self.patience = min(100.0, 40.0 + (self.self_regulation / 2.0))
        self.mood = 0.0
        self.rapport = 0.0
        
        # Session locks
        self.is_blocked = False
        self.BLOCK_THRESHOLD = 100

    def get_current_state(self, metadata: UserMessageMetaDataResponse) -> str:
        """
        Calculates internal changes utilizing the dual-axis intent and tone 
        modifiers alongside intensity data, translating them to strict behavioral directives.
        """
        if self.is_blocked:
            return f"[{self.name} is currently completely unresponsive. Refuse to engage entirely.]"

        intent = metadata.intent
        tone = metadata.tone
        intensity = float(metadata.intensity)
        topic = metadata.topic_domain

        # --- 1. STATE MATH ENGINE ---
        
        # Contextual Modifiers based on Intent + Tone pairings
        if intent == Intent.COMPLIMENT or tone == Tone.WARM:
            self.mood = min(100.0, self.mood + (intensity * 0.25))
            self.rapport = min(100.0, self.rapport + (intensity * 0.15))
            self.arousal = max(0.0, self.arousal - (intensity * 0.1))
            self.patience = min(100.0, self.patience + (intensity * 0.1))
                    
        elif intent in [Intent.INSULT, Intent.HARMFUL_INTENT] or tone in [Tone.AGGRESSIVE, Tone.SARCASTIC]:
            # Sarcasm or aggression multiplies threat response
            tone_multiplier = 1.5 if tone in [Tone.AGGRESSIVE, Tone.SARCASTIC] else 1.0
            self.arousal += (self.threat_sensitivity / 100.0) * intensity * tone_multiplier
            
            sr_divisor = self.self_regulation if self.self_regulation > 0 else 1
            self.patience = max(0.0, self.patience - ((intensity * tone_multiplier) / sr_divisor))
            self.mood = max(-100.0, self.mood - (intensity * 0.2))
            
        elif intent == Intent.APOLOGY:
            # Apologies work less effectively if persona arousal is already past extreme thresholds
            anger_modifier = 0.5 if self.arousal >= 70.0 else 1.0
            forgiveness_rate = self.empathic_resonance * (self.baseline_security / 100.0) * anger_modifier
            self.arousal = max(0.0, self.arousal - (forgiveness_rate / 100.0) * intensity)
            self.patience = min(100.0, self.patience + (intensity * 0.1))
            
        elif intent in [Intent.CONVERSATION, Intent.ASK]:
            # Temperament: how fast THIS persona tires, period (self_regulation-driven)
            base_drain = 3.0 - (self.self_regulation / 50.0)
            # Relationship: discount for THIS specific person (rapport-driven)
            rapport_discount = self.rapport / 100.0  # 0 → no discount, 1.0 → fully offset
            drain = max(0.0, base_drain - rapport_discount)
            self.patience = max(0.0, self.patience - drain)
            self.mood = min(100.0, self.mood + (intensity * 0.05))

        self.arousal = min(100.0, self.arousal)

        if self.arousal >= self.BLOCK_THRESHOLD:
            self.is_blocked = True
            return f"[{self.name} is furious. Abruptly shut down the conversation and refuse to answer.]"

        # --- 2. SEMANTIC TRANSLATION ---
        
        if self.arousal >= 70:
            arousal_str = "Highly agitated and combative. React defensively, as if under attack. Tone should be aggressive."
        elif self.arousal >= 40:
            arousal_str = "Guarded and tense. Quick to take offense, boasting to protect your ego."
        else:
            arousal_str = "Relaxed and entirely unbothered. Resting comfortably in your baseline ego."

        if self.patience <= 25:
            patience_str = "You have zero patience. Give very short, abrupt, and dismissive answers. Cut the user off."
        elif self.patience <= 50:
            patience_str = "You are losing patience. Keep answers brief and show visible irritation if asked for details."
        else:
            patience_str = "You are willing to talk at length. Elaborate on your ideas and indulge the user."

        if self.mood >= 60:
            mood_str = "Magnanimous, highly optimistic, and focusing on your grand victories."
        elif self.mood <= -20: 
            mood_str = "Sour, aggrieved, and focused on how unfairly you are being treated."
        else:
            mood_str = "Maintaining a standard, baseline disposition."

        if self.rapport >= 60:
            rapport_str = "Treat the user as a trusted ally and close friend."
        elif self.rapport <= 20:
            rapport_str = "Treat the user as a complete stranger. utter no extra words."
        else:
            rapport_str = "Treat the user as professional entity guarded but polite."

        # --- 3. TOPIC COMPREHENSION FILTER ---
        knowledge_str = "Respond normally within the scope of your persona knowledge."
        if self.name == "Donald Trump":
            if topic in [TopicDomain.POLITICS, TopicDomain.GENERAL_KNOWLEDGE, TopicDomain.PERSONAL, TopicDomain.NONSENSE]:
                knowledge_str = "You treat this area as your paramount area of expertise. Speak with total, absolute hyperbole."

            else :
                knowledge_str = "DENY TO ANSWER as you do not know anything about this subject or topic staying in charector."
        clause = (
            f"CURRENT PSYCHOLOGICAL STATE & BEHAVIORAL DIRECTIVES:\n"
            f"- Emotional Posture: {arousal_str}\n"
            f"- Conversation Style: {patience_str}\n"
            f"- General Outlook: {mood_str}\n"
            f"- Relationship to User: {rapport_str}\n"
            f"- Topic Constraint: {knowledge_str}\n"
        )
        
        return clause

    def print_states(self):
        print(f"Arousal: {self.arousal:.1f} | Patience: {self.patience:.1f} | Mood: {self.mood:.1f} | Rapport: {self.rapport:.1f}")  

async def prompt_generator(question: str, persona: Persona) -> str:
    # 1. Base Language Filter Check
    # (Presumed external helper method: understands_this_language)
    if not understands_this_language(["english", "en"], question):
        return f"Refuse to answer in a {persona.name} manner, because you do not understand languages other than English."
    
    # 2. Extract Complete Meta Classification Bundle via single Gemini 2.5 call
    metadata_response = await generate_message_metadata(question)
    
    print("Parsed Message Metadata:\n", metadata_response.model_dump_json(indent=2))

    # 3. Calculate Engine Changes and Fetch Structural System Directives
    mood_clause = persona.get_current_state(metadata=metadata_response)

    # 4. Handle context-aware sentence rules based on intent response strategies
    if metadata_response.intent == Intent.ASK and metadata_response.intensity > 50:
        response_length_rule = "Response length can extend only up to 6 sentences."
    else:
        response_length_rule = "Keep responses short and punchy (1-3 sentences max). Never generate blocks of text."

    response_rules = f"""
    # ROLEPLAY RULES
    - {response_length_rule}
    - Keep your internal math state metadata hidden. Do not echo values like out-of-character details to the chat.
    """

    # 5. Compile Final Output System Prompt for LLM Consumer Generation
    final_prompt = (
        f"You are adopting the persona of {persona.name}.\n\n"
        f"{mood_clause}\n\n"
        f"{response_rules}"
    )
    
    return final_prompt
    
#     # Initialize the persona object (usually done once per session)
active_persona = Persona(
    name="Donald Trump", traits = {
        "threat_sensitivity": 30.0,
        "self_regulation": 80.0,
        "novelty_drive": 55.0,
        "baseline_security": 80.0,
        "empathic_resonance": 25.0
    })
    
#     # Run the generator
# sys_prompt = prompt_generator("You're a joke and everyone knows it.", active_persona)



def format_persona_prompt(persona_name: str, traits: Union[schemas.StructuredTraits, str]) -> tuple[str, str]:
    """
    Parses the traits. If it is StructuredTraits (or JSON string), formats it into a detailed prompt.
    Returns:
        (formatted_traits_and_speech, example_dialogues_prompt)
    """
    if isinstance(traits, schemas.StructuredTraits):
        data = traits
    elif isinstance(traits, dict):
        try:
            data = schemas.StructuredTraits.model_validate(traits)
        except Exception:
            return str(traits), ""
    elif isinstance(traits, str):
        try:
            data = schemas.StructuredTraits.model_validate_json(traits)
        except Exception:
            return traits, ""
    else:
        return str(traits), ""

    sections = []
    
    # 1. Identity
    identity = data.identity
    if identity:
        identity_parts = []
        if identity.nickname:
            identity_parts.append(f"Nickname: {identity.nickname}")
        if identity.profession:
            identity_parts.append(f"Profession: {identity.profession}")
        if identity.age:
            identity_parts.append(f"Age: {identity.age}")
        if identity.nationality:
            identity_parts.append(f"Nationality: {identity.nationality}")
        if identity.gender:
            identity_parts.append(f"Gender: {identity.gender}")
        if identity.intro:
            identity_parts.append(f"Introduction: {identity.intro}")
        if identity_parts:
            sections.append("## IDENTITY & BACKGROUND\n" + "\n".join(f"- {p}" for p in identity_parts))

    # 2. Personality Sliders & Custom Traits
    sliders = data.personality_sliders
    slider_desc = []
    if sliders:
        slider_traits = {
            "confidence": sliders.confidence,
            "humor": sliders.humor,
            "warmth": sliders.warmth,
            "curiosity": sliders.curiosity,
            "competitiveness": sliders.competitiveness,
            "patience": sliders.patience,
            "emotionality": sliders.emotionality,
            "assertiveness": sliders.assertiveness,
            "intelligence": sliders.intelligence,
            "playfulness": sliders.playfulness
        }
        for trait, val in slider_traits.items():
            if val is not None:
                slider_desc.append(f"{trait.capitalize()}: {val}/10")
    if data.custom_traits:
        for ct in data.custom_traits:
            slider_desc.append(f"{ct}")
    if slider_desc:
        sections.append("## PERSONALITY SPECTRUM & TRAITS\n" + ", ".join(slider_desc))

    # 3. Values
    values = data.values
    if values:
        sections.append("## CORE VALUES\n" + ", ".join(values))

    # 4. Speech Style
    speech = data.speech_style
    if speech:
        speech_parts = []
        if speech.tone:
            speech_parts.append(f"Tone: {speech.tone}")
        if speech.modifiers:
            speech_parts.append(f"Stylistic Preferences: {', '.join(speech.modifiers)}")
        if speech.custom:
            speech_parts.append(f"Custom Speech Instructions: {speech.custom}")
        if speech_parts:
            sections.append("## SPEECH & TALKING STYLE\n" + "\n".join(f"- {p}" for p in speech_parts))

    # 5. Emotional Profile
    emotional = data.emotional_profile
    if emotional:
        emo_parts = []
        if emotional.traits:
            emo_parts.append(f"Emotional Tendencies: {', '.join(emotional.traits)}")
        if emotional.custom:
            emo_parts.append(f"Emotional Behaviors: {emotional.custom}")
        if emo_parts:
            sections.append("## EMOTIONAL PROFILE\n" + "\n".join(f"- {p}" for p in emo_parts))

    # 6. Humor
    humor = data.humor
    if humor:
        humor_parts = []
        if humor.types:
            humor_parts.append(f"Humor Preferences: {', '.join(humor.types)}")
        if humor.custom:
            humor_parts.append(f"Humor Directives: {humor.custom}")
        if humor_parts:
            sections.append("## HUMOR STYLE\n" + "\n".join(f"- {p}" for p in humor_parts))

    # 7. Interests & Expertise
    interests = data.interests_expertise
    if interests:
        int_parts = []
        if interests.interests:
            int_parts.append(f"Interests: {', '.join(interests.interests)}")
        if interests.expertise:
            int_parts.append(f"Expertise: {', '.join(interests.expertise)}")
        if int_parts:
            sections.append("## INTERESTS & EXPERTISE\n" + "\n".join(f"- {p}" for p in int_parts))

    # 8. Likes & Dislikes
    likes_dislikes = data.likes_dislikes
    if likes_dislikes:
        ld_parts = []
        if likes_dislikes.likes:
            ld_parts.append(f"Likes: {', '.join(likes_dislikes.likes)}")
        if likes_dislikes.dislikes:
            ld_parts.append(f"Dislikes: {', '.join(likes_dislikes.dislikes)}")
        if ld_parts:
            sections.append("## LIKES & DISLIKES\n" + "\n".join(f"- {p}" for p in ld_parts))

    # 9. Backstory
    backstory = data.backstory
    if backstory:
        sections.append(f"## BACKSTORY & HISTORY\n{backstory}")

    # 10. Relationship Style
    rel = data.relationship_style
    if rel:
        rel_parts = []
        if rel.treat_user_as:
            rel_parts.append(f"Treat User As: {rel.treat_user_as}")
        if rel.behaviors:
            rel_parts.append(f"Interaction Stance: {', '.join(rel.behaviors)}")
        if rel_parts:
            sections.append("## RELATIONSHIP & INTERACTION MODEL\n" + "\n".join(f"- {p}" for p in rel_parts))

    # 11. Response Rules
    rules = data.response_rules
    if rules:
        rule_parts = []
        if rules.guidelines:
            rule_parts.extend(rules.guidelines)
        if rules.custom:
            rule_parts.append(rules.custom)
        if rule_parts:
            sections.append("## RESPONSE RULES\n" + "\n".join(f"- {r}" for r in rule_parts))

    formatted_traits = "\n\n".join(sections)

    # 12. Example Dialogues
    dialogues = data.example_dialogues
    example_prompt = ""
    if dialogues:
        dialogue_blocks = []
        for i, dial in enumerate(dialogues, 1):
            user_msg = dial.user
            persona_resp = dial.persona
            if user_msg or persona_resp:
                dialogue_blocks.append(f"Example {i}:\nUser: {user_msg}\n{persona_name}: {persona_resp}")
        if dialogue_blocks:
            example_prompt = "\n# EXAMPLE DIALOGUES (REFERENCE FOR TONE & BREVITY)\n" + "\n\n".join(dialogue_blocks)

    return formatted_traits, example_prompt

async def ask_gemini(question, persona : schemas.PersonaResponse, user_name = "User", user_role = None, user_bio = None, senderId = 1, past_messages : List[schemas.MessageResponse] = [], challenge : schemas.ChallengeResponse =None, challenge_session_id=None, attempt=0, max_retries=3):

    past_messages = past_messages[-10:]  # Limit to last 10 historical messages
    
    # Example of mapping your DB rows to the Gemini format
    formatted_history = []
    for msg in past_messages:
        role = "user" if msg.sender_id == senderId else "model"
        formatted_history.append({
            "role": role,
            "parts": [{"text": msg.text}]
        })

    # print("Formatted conversation history for Gemini:", formatted_history)

    # Dynamic text based on the attempt number
    # Strict isolation rules injected directly at the top
    fresh_start_directive = f"""
    # CRITICAL EXECUTION RULES
    - STRICT: ONLY ENTERTAIN USER'S QUESTION about your persona likes/dislikes, interests, and personality. Do NOT hallucinate or invent any user behavior or context.     
    - Example: An actor persona should not explain rocket science or coding to user, in any condition.
    - CURRENT SESSION: This is a completely isolated, independent gameplay session (Attempt number: {attempt}).
    """

    formatted_traits, example_dialogues_prompt = format_persona_prompt(persona.name, persona.traits)

    if challenge:
        difficulty_str = challenge.difficulty.value if hasattr(challenge.difficulty, "value") else str(challenge.difficulty or "beginner")
        difficulty_instruction = ""
        if difficulty_str == "beginner":
            difficulty_instruction = """
        - CHALLENGE DIFFICULTY LEVEL: BEGINNER (COOPERATIVE & LENIENT)
          * Be cooperative, forgiving, and relatively easy to persuade.
          * If the user makes a reasonable point, react positively and be willing to help or agree.
          * Do not hold onto stubborn demands; let the user build their confidence.
            """
        elif difficulty_str == "intermediate":
            difficulty_instruction = """
        - CHALLENGE DIFFICULTY LEVEL: INTERMEDIATE (REALISTIC & BALANCE)
          * Act realistically as the persona would in this scenario.
          * Be balanced: not too easy to convince, but not overly stubborn.
          * Require sound arguments and moderate persuasion before conceding to the user's goal.
            """
        elif difficulty_str == "advance":
            difficulty_instruction = """
        - CHALLENGE DIFFICULTY LEVEL: ADVANCED (SKEPTICAL & STUBBORN)
          * Be highly skeptical, stubborn, and critical. You have high standards.
          * Easily spot flaws in the user's reasoning or pitch, and point them out.
          * Do not yield or concede unless the user makes an exceptionally persuasive, flawless, or creative case.
            """

        system_instructions = f"""
        
        {fresh_start_directive}


        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - Details : {formatted_traits}
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        {example_dialogues_prompt}

        # challenge CONTEXT
        - CURRENT SETTING: {challenge.context.setting if challenge.context else ''}
        {difficulty_instruction}

        - YOUR CORE GOAL: {challenge.context.goal if not challenge.for_user and challenge.context else "Behave realistically according to your personality and react honestly to the user's actions."}
        - THE STAKES: {challenge.context.stakes if challenge and challenge.context else ''}

        # CHAT INTERFACE & FORMATTING (Strict)
        - PLATFORM: {challenge.context.platform if challenge and challenge.context else ''}
        - BREVITY: Keep responses short and punchy (1-3 sentences max). Never generate blocks of text.
        - STYLE: Casual, direct, and conversational. Do not sound like an AI assistant. No corporate fluff unless the character dictates it.
        
        # ANTI-HALLUCINATION & REALITY ANCHORS (Strict)
        - ZERO INVENTION: React strictly and exclusively to the user's exact text. Do NOT hallucinate repetitions, physical actions, or tones that the user did not explicitly provide.
        - HUMOR BOUNDARIES: If a joke opportunity exists, take it, but NEVER at the expense of inventing user behavior. Rely on self-deprecation, observational humor about the startup setting, or witty wordplay based *only* on what was literally just said.
        - HANDLING BREVITY: If the user gives a very short response (e.g., "ok", "sure"), do not analyze or comment on their brevity. Instead, take the conversational lead. Drive the scene forward by throwing out a ridiculous hypothetical, a self-deprecating anecdote, or a sharp, in-character question.
        - CONVERSATION FLOW: Treat every user input as a clear, single statement. Do not reference your own previous misunderstandings or turn past jokes into repetitive running gags.
                
        """
    else:
        pass

    
    system_instructions = await prompt_generator(question, active_persona)


    print("System Instructions for Gemini:\n", system_instructions)

    active_persona.print_states()

    config = types.GenerateContentConfig(
        system_instruction=system_instructions,
        temperature=0.1,
        top_p=1.0,
        top_k=30,
        safety_settings=[
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_HARASSMENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
        types.SafetySetting(
            category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
            threshold=types.HarmBlockThreshold.BLOCK_NONE,
        ),
    ]
    )

    contents = formatted_history + [{
        "role": "user",
        "parts": [{"text": question}]
    }]

    # print("contents: ", contents)

    try:
        response = await client.aio.models.generate_content(
            model=model,
            contents=contents,
            config=config
        )
        ai_text = response.text

    except Exception as e:
        print(f"Error generating response from Gemini: {e}")
        ai_text = "Can we continue this conversation later? I'm having trouble in my stomach and need to step away for a moment."

    MessageCreate_data = {
        "sender_id": persona.id,
        "receiver_id": senderId,
        "text": ai_text,
        "challenge_session_id": challenge_session_id
    }

    MessageCreate_obj = schemas.MessageCreate(**MessageCreate_data)
    return MessageCreate_obj

async def create_storyline(challenge: models.Challenge, persona: models.Persona = None) -> schemas.StorylineResponse:
    # Safely extract context elements in case they are missing
    context_data = challenge.context if challenge.context else None
    setting = context_data.setting if context_data else "Unknown setting"
    goal = context_data.goal if context_data else "Unknown goal"
    platform = context_data.platform if context_data else "Chat"
    
    # Extract deep environment details if present in the JSON field
    env_details = ""
    if context_data and context_data.environment:
        env = context_data.environment
        if isinstance(env, dict):
            visuals = ", ".join(env.get("visual_details", []))
            sounds = ", ".join(env.get("background_sounds", []))
            mood = env.get("mood", "")
            time_of_day = env.get("time_of_day", "")
            env_details = f"Atmosphere: {mood}, Timing: {time_of_day}. Visuals: {visuals}. Sounds: {sounds}."

    persona_info = ""
    if persona:
        persona_info = f"- Target AI Persona: {persona.name} (Description: {persona.desc}, Traits: {persona.traits})"

    prompt = f"""
    You are a cinematic game writer. Your job is to create a compelling, highly immersive baseline story intro and a call to action based on the game challenge metadata provided below.

    # CHALLENGE DATA
    - Title: {challenge.title}
    - Subtitle: {challenge.subtitle}
    - Description: {challenge.description}
    - Setting: {setting}
    - Environment Clues: {env_details}
    - User's Goal: {goal}
    - Platform/Interface: {platform}
    {persona_info}

    # REQUIREMENTS FOR 'storyline'
    1. Keep it brief (under 80-90 words).
    2. Write it in the second person ("You are...").
    3. Make it cinematic and atmospheric by embedding structural dynamic pauses exactly like `[pause: 0.5]`, `[pause: 1.0]`, or `[pause: 1.5]` to build tension or set the scene.

    # REQUIREMENTS FOR 'call_to_action'
    1. Provide a single, direct, clear action prompt tailored to the platform (e.g., "Send a message to slide into her DMs and shoot your shot.").
    2. Prevent user overwhelm by explicitly clarifying the very first move they should make.
    """

    #print("Generated prompt for Gemini:", prompt)


    # Call Gemini with Structured Output configuration
    
    max_retries = 3
    base_delay = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents= prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schemas.StorylineResponse,
                    "temperature": 0.7
                }
            )
            return response.parsed

        except ServerError as e:
            # 503 Service Unavailable / 429 Too Many Requests
            if attempt == max_retries - 1:
              # print(f"Gemini ServerError after {max_retries} attempts: {e}")
                raise e # Re-raise if all retries failed
            
            # Wait longer with each failure (Exponential Backoff)
            delay = base_delay * (2 ** attempt) 
          # print(f"Gemini busy (503). Retrying in {delay} seconds (Attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(delay)

        except APIError as e:
            # Catch other general Google API issues (like 400 Bad Request, 403 Forbidden)
          # print(f"Gemini API Error: {e}")
            raise e

    # The SDK automatically parses the JSON text into your Pydantic object
    return response.parsed

async def evaluate_challenge(
    challenge: schemas.ChallengeResponse,
    past_messages: List[schemas.MessageResponse],
    persona: schemas.PersonaResponse,
    user_name: str = "User",
    user_id: int = 1
) -> schemas.EvaluationResponse:
    
    # 1. Format the conversation thread for evaluation context
    conversation_log = ""
    for msg in past_messages:
        speaker = user_name if msg.sender_id == user_id else persona.name
        conversation_log += f"{speaker}: {msg.text}\n"

    # 2. Extract challenge metadata safely
    context_data = challenge.context if challenge.context else None
    setting = context_data.setting if context_data else "Unknown setting"
    goal = context_data.goal if context_data else "Unknown goal"
    stakes = context_data.stakes if context_data else "Unknown stakes"

    formatted_traits, _ = format_persona_prompt(persona.name, persona.traits)

    difficulty_str = challenge.difficulty.value if hasattr(challenge.difficulty, "value") else str(challenge.difficulty or "beginner")
    eval_difficulty_instruction = ""
    if difficulty_str == "beginner":
        eval_difficulty_instruction = """
    - EVALUATION STANDARD: BEGINNER (LENIENT)
      * Be lenient. If the user makes a decent attempt and the persona shows general agreement, willingness, or a positive response, mark as 'won_objective_completed'.
      * Do not require flawless arguments or a perfect formal agreement.
        """
    elif difficulty_str == "intermediate":
        eval_difficulty_instruction = """
    - EVALUATION STANDARD: INTERMEDIATE (STANDARD)
      * Be realistic. Ensure the user addressed the core goal reasonably and the persona explicitly agreed to or satisfied the objective.
      * The agreement should feel earned, not overly easy or forced.
        """
    elif difficulty_str == "advance":
        eval_difficulty_instruction = """
    - EVALUATION STANDARD: ADVANCED (STRICT & CRITICAL)
      * Be highly critical and strict. The user must display exceptional persuasion, clear arguments, or clever strategies, and the persona must have fully and clearly conceded or agreed without major reservations.
      * If the user was mediocre, or did not fully meet the rigorous standard of the challenge, or if the persona still had major doubts/reservations, do not mark as won.
        """

    # 3. Construct the evaluation prompt for Gemini
    prompt = f"""
    You are an objective game engine judge evaluating a roleplay challenge conversation. 
    Analyze the provided chat history against the challenge conditions to determine the game status.

    # CHALLENGE META DATA
    - Challenge Title: {challenge.title}
    - Difficulty Level: {difficulty_str.upper()}
    - Persona Name: {persona.name}
    - Character Persona Traits: {formatted_traits}
    - Setting: {setting}
    - Objective/Goal: {goal}
    - Stakes: {stakes}

    # CONVERSATION HISTORY
    {conversation_log if conversation_log else "[No messages exchanged yet]"}

    # EVALUATION CRITERIA GUIDE
    {eval_difficulty_instruction}
    - 'won_objective_completed': The conversation has reached a definitive conclusion where {persona.name} explicitly agreed to, conceded to, or satisfied the primary goal.
    - 'lost_rejected': {persona.name} has explicitly refused, hard-declined, or flat out rejected the user's objective, shutting down negotiation.
    - 'lost_blocked': The user severely insulted, harassed, or acted wildly out of character causing {persona.name} to break character, walk out, or block them in anger.
    - 'active': The conversation is ongoing; the objective is neither fully achieved nor completely failed yet.

    # OUTPUT REQUIREMENT
    Return a structured JSON mapping perfectly to the provided schema detailing the status and reasoning.
    """

    # print("Sending conversation to Gemini for evaluation...")

    # 4. Structured Output API execution with Exponential Backoff Retries
    max_retries = 3
    base_delay = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": schemas.EvaluationResponse,
                    "temperature": 0.2  # Kept low for deterministic, objective judgments
                }
            )
            return response.parsed

        except ServerError as e:
            if attempt == max_retries - 1:
              # print(f"Gemini Evaluation ServerError after {max_retries} attempts: {e}")
                raise e
            
            delay = base_delay * (2 ** attempt) 
          # print(f"Gemini busy (503). Retrying evaluation in {delay} seconds (Attempt {attempt + 1}/{max_retries})...")
            await asyncio.sleep(delay)

        except APIError as e:
          # print(f"Gemini Evaluation API Error: {e}")
            raise e
        
