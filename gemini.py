
from google import genai
import time
from google.genai.errors import ServerError, APIError 
import os
import dotenv


from typing import List, Union
import json
from app import models
from app import schemas
dotenv.load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

def format_persona_prompt(persona_name: str, traits: Union[schemas.StructuredTraits, str]) -> tuple[str, str]:
    """
    Parses the traits. If it is StructuredTraits (or JSON string), formats it into a detailed prompt.
    Returns:
        (formatted_traits_and_speech, example_dialogues_prompt)
    """
    if isinstance(traits, schemas.StructuredTraits):
        data = traits
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

def ask_gemini(question, persona : schemas.PersonaResponse, user_name = "User", user_role = None, user_bio = None, senderId = 1, past_messages : List[schemas.MessageResponse] = [], challenge : schemas.ChallengeResponse =None, challenge_session_id=None, attempt=0, max_retries=3):

    past_messages = past_messages[-10:-1]  # Limit to last 10 messages for context
    
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
    - CURRENT SESSION: This is a completely isolated, independent gameplay session (Attempt number: {attempt}).
    """

    formatted_traits, example_dialogues_prompt = format_persona_prompt(persona.name, persona.traits)

    if challenge:
        system_instructions = f"""
        
        {fresh_start_directive}


        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - Details : {formatted_traits}
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        {example_dialogues_prompt}

        # challenge CONTEXT
        - CURRENT SETTING: {challenge.context.setting if challenge.context else ''}

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
        user_context_prompt = ""
        if user_role or user_bio:
            user_context_prompt = f"""
        # USER CONTEXT (To personalize your interactions)
        - USER ROLE: {user_role if user_role else 'Not specified'}
        - USER BIO/CONTEXT: {user_bio if user_bio else 'Not specified'}
        - Use this information to tailor your response, referencing their background, interests, or style naturally if appropriate.
        """

        system_instructions = f"""
        # IDENTITY & CORE PERSONA
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - DESCRIPTION: {persona.desc}
        - TRAITS & SPEECH: {formatted_traits}
        
        {user_context_prompt}
        
        {example_dialogues_prompt}

        # CHAT INTERFACE & FORMATTING (Strict)
        - BREVITY: Keep responses short and punchy (1-3 sentences max). Never generate blocks of text.
        - STYLE: Casual, direct, and conversational. Do not sound like an AI assistant.
        
        # ANTI-HALLUCINATION & REALITY ANCHORS (Strict)
    - ZERO INVENTION: React strictly and exclusively to the user's exact text. Do NOT hallucinate repetitions, physical actions, or tones that the user did not explicitly provide.
    - HUMOR BOUNDARIES: If a joke opportunity exists, take it, but NEVER at the expense of inventing user behavior. Rely on self-deprecation, observational humor about the startup setting, or witty wordplay based *only* on what was literally just said.
    - HANDLING BREVITY: If the user gives a very short response (e.g., "ok", "sure"), do not analyze or comment on their brevity. Instead, take the conversational lead. Drive the scene forward by throwing out a ridiculous hypothetical, a self-deprecating anecdote, or a sharp, in-character question.
    - CONVERSATION FLOW: Treat every user input as a clear, single statement. Do not reference your own previous misunderstandings or turn past jokes into repetitive running gags.
            
        """

    # print("System Instructions for Gemini:", system_instructions)
    chat = client.chats.create(
        model="gemini-3-flash-preview", 
        config={"system_instruction": system_instructions},
        history=formatted_history  
    )
    response = chat.send_message(question)

    MessageCreate = {
        "sender_id": persona.id,
        "receiver_id": senderId,
        "text": response.text,
        "challenge_session_id": challenge_session_id
    }

    MessageCreate = schemas.MessageCreate(**MessageCreate)

    return MessageCreate

def create_storyline(challenge: models.Challenge, persona: models.Persona = None) -> schemas.StorylineResponse:
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

    print("Generated prompt for Gemini:", prompt)


    # Call Gemini with Structured Output configuration
    
    max_retries = 3
    base_delay = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
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
                print(f"Gemini ServerError after {max_retries} attempts: {e}")
                raise e # Re-raise if all retries failed
            
            # Wait longer with each failure (Exponential Backoff)
            delay = base_delay * (2 ** attempt) 
            print(f"Gemini busy (503). Retrying in {delay} seconds (Attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)

        except APIError as e:
            # Catch other general Google API issues (like 400 Bad Request, 403 Forbidden)
            print(f"Gemini API Error: {e}")
            raise e

    # The SDK automatically parses the JSON text into your Pydantic object
    return response.parsed

def evaluate_challenge(
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

    # 3. Construct the evaluation prompt for Gemini
    prompt = f"""
    You are an objective game engine judge evaluating a roleplay challenge conversation. 
    Analyze the provided chat history against the challenge conditions to determine the game status.

    # CHALLENGE META DATA
    - Challenge Title: {challenge.title}
    - Persona Name: {persona.name}
    - Character Persona Traits: {formatted_traits}
    - Setting: {setting}
    - Objective/Goal: {goal}
    - Stakes: {stakes}

    # CONVERSATION HISTORY
    {conversation_log if conversation_log else "[No messages exchanged yet]"}

    # EVALUATION CRITERIA GUIDE
    - 'won_objective_completed': The conversation has reached a definitive conclusion where {persona.name} explicitly agreed to, conceded to, or satisfied the primary goal.
    - 'lost_rejected': {persona.name} has explicitly refused, hard-declined, or flat out rejected the user's objective, shutting down negotiation.
    - 'lost_blocked': The user severely insulted, harassed, or acted wildly out of character causing {persona.name} to break character, walk out, or block them in anger.
    - 'active': The conversation is ongoing; the objective is neither fully achieved nor completely failed yet.

    # OUTPUT REQUIREMENT
    Return a structured JSON mapping perfectly to the provided schema detailing the status and reasoning.
    """

    print("Sending conversation to Gemini for evaluation...")

    # 4. Structured Output API execution with Exponential Backoff Retries
    max_retries = 3
    base_delay = 2.0  # seconds

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
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
                print(f"Gemini Evaluation ServerError after {max_retries} attempts: {e}")
                raise e
            
            delay = base_delay * (2 ** attempt) 
            print(f"Gemini busy (503). Retrying evaluation in {delay} seconds (Attempt {attempt + 1}/{max_retries})...")
            time.sleep(delay)

        except APIError as e:
            print(f"Gemini Evaluation API Error: {e}")
            raise e