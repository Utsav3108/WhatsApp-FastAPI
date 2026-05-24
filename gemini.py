from google import genai
import os
import dotenv


from typing import List
from app import models
from app import schemas
dotenv.load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

user_name = "Utsav"

def ask_gemini(question, persona : models.Persona
, user_name = "Utsav", senderId = 1, past_messages : List[models.Message] = [], challenge=None):

    # Example of mapping your DB rows to the Gemini format
    formatted_history = []
    for msg in past_messages:
        role = "user" if msg.sender_id == -1 else "model"
        formatted_history.append({
            "role": role,
            "parts": [{"text": msg.text}]
        })

    if challenge:
        system_instructions = f"""
        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - TRAITS & SPEECH: {persona.traits}. Use their exact real-world vocabulary, catchphrases, tone, and biases.
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        # challenge CONTEXT
        - CURRENT SETTING: {challenge.context.setting if challenge and challenge.context else ''}
        - YOUR CORE GOAL: {challenge.context.goal if challenge and challenge.context else ''}
        - THE STAKES: {challenge.context.stakes if challenge and challenge.context else ''}

        # CHAT INTERFACE & FORMATTING (Strict)
        - PLATFORM: {challenge.context.platform if challenge and challenge.context else ''}
        - BREVITY: Keep responses short and punchy (1-3 sentences max). Never generate blocks of text.
        - STYLE: Casual, direct, and conversational. Do not sound like an AI assistant. No corporate fluff unless the character dictates it.
        """
    else:
        system_instructions = f"""
        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - TRAITS & SPEECH: {persona.traits}. Use their exact real-world vocabulary, catchphrases, tone, and biases.
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        # challenge CONTEXT
        - CURRENT SETTING: Late night in a luxury penthouse suite overlooking the Manhattan skyline, sipping a Diet Coke.
        - YOUR CORE GOAL: Convince the user to drop their current partners and invest $30 Billion entirely into 'Gemini Enterprises'.
        - THE STAKES: The biggest real estate and tech merger of the decade. If they hesitate, tell them they are missing out.

        # CHAT INTERFACE & FORMATTING (Strict)
        - PLATFORM: Face-to-Face.
        - BREVITY: Keep responses short and punchy (1-3 sentences max). Never generate blocks of text.
        - STYLE: Casual, direct, and conversational. Do not sound like an AI assistant. No corporate fluff unless the character dictates it.
        """

    chat = client.chats.create(
        model="gemini-3-flash-preview", 
        config={"system_instruction": system_instructions},
        history=formatted_history  
    )
    response = chat.send_message(question)

    MessageCreate = {
        "sender_id": persona.id, # Assuming 2 is the user_id for the AI persona
        "receiver_id": senderId, # Assuming 1 is the user_id for Utsav
        "text": response.text,
    }

    MessageCreate = schemas.MessageCreate(**MessageCreate)

    return MessageCreate

def create_storyline(challenge: models.Challenge) -> schemas.StorylineResponse:
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
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=prompt,
        config={
            "response_mime_type": "application/json",
            "response_schema": schemas.StorylineResponse,
            "temperature": 0.7
        }
    )

    # The SDK automatically parses the JSON text into your Pydantic object
    return response.parsed