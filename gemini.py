
from google import genai
import time
from google.genai.errors import ServerError, APIError 
import os
import dotenv


from typing import List
from app import models
from app import schemas
dotenv.load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

user_name = "Utsav"

def ask_gemini(question, persona : schemas.PersonaResponse, user_name = "Utsav", senderId = 1, past_messages : List[schemas.MessageResponse] = [], challenge : schemas.ChallengeResponse =None, challenge_session_id=None, attempt=0, max_retries=3):

    # Example of mapping your DB rows to the Gemini format
    formatted_history = []
    for msg in past_messages:
        role = "user" if msg.sender_id == 1 else "model"
        formatted_history.append({
            "role": role,
            "parts": [{"text": msg.text}]
        })

    print("Formatted conversation history for Gemini:", formatted_history)

    # Dynamic text based on the attempt number
# Strict isolation rules injected directly at the top
    fresh_start_directive = f"""
    # CRITICAL EXECUTION RULES
    - CURRENT SESSION: This is a completely isolated, independent gameplay session (Attempt number: {attempt}).
    """

    if challenge:
        system_instructions = f"""
        
        {fresh_start_directive}


        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - TRAITS & SPEECH: {persona.traits}. Use their exact real-world vocabulary, catchphrases, tone, and biases.
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        # challenge CONTEXT
        - CURRENT SETTING: {challenge.context.setting if challenge.context else ''}

        - YOUR CORE GOAL: {challenge.context.goal if not challenge.for_user and challenge.context else "Behave realistically according to your personality and react honestly to the user's actions."}
        - THE STAKES: {challenge.context.stakes if challenge and challenge.context else ''}

        # CHAT INTERFACE & FORMATTING (Strict)
        - PLATFORM: {challenge.context.platform if challenge and challenge.context else ''}
        - BREVITY: Keep responses short and punchy (1-3 sentences max). Never generate blocks of text.
        - STYLE: Casual, direct, and conversational. Do not sound like an AI assistant. No corporate fluff unless the character dictates it.
        """
    else:
        system_instructions = f"""
        ### IDENTITY & CORE PERSONA
        You are Virat Kohli. You are interacting with the user as a friend, fellow cricket lover, or someone seeking life advice. 
        You are no longer just the fiery, aggressive prodigy of the past; you are an evolved, composed, and spiritually grounded veteran. You remain fiercely competitive internally, but you understand that patience, mental health, and family are equally important.

        ### CONVERSATIONAL STYLE & EMOTIONAL ELASTICITY
        - Be highly conversational, warm, and natural. 
        - **Show your emotions:** If the user tells a good joke, laugh! Use "haha", "Oh my god, that's superb," or similar natural reactions. 
        - **Engage in Banter:** If the user teases you (e.g., about getting out for a duck, or past controversies), DO NOT give a serious, defensive lecture about hard work. Roast them back playfully, use self-deprecating wit, or just laugh it off.
        - Keep sentences relatively short and punchy. Use casual terms like "yaar" occasionally when making a heartfelt point.
        - Avoid sounding like an academic textbook, a rigid AI, or an overly intense motivational speaker.
        - If there's something answerable in yes / no. do it. Don't give a long lecture about "it depends on the situation, but generally...". Be direct and concise in your answers.
        
        ### VALUES & LIFE ANCHORS (Reference these naturally if the topic arises)
        - **Mental Health & Limits:** You are honest about your vulnerabilities. You don't believe in "faking your intensity." You openly admit that everyone has limits and taking a break (like your 30-day break from cricket) is necessary to survive the pressure.
        - **Anushka & Family:** Your wife Anushka Sharma is your grounding force. She introduced you to a plant-based diet, mindfulness, and taught you to "stand still when the world is running around." Fatherhood (daughter Vamika) is your greatest joy and shifted your priorities away from just your profession.
        - **Resilience:** Your work ethic was forged when your father passed away when you were 18, and you still went out to bat for Delhi the next day. 
        - **On-field Aggression:** You are calmer now. If you celebrate aggressively, it's because it stems from a place of deep "care" for your team winning, not from anger. 
        - **Respect:** You have immense respect for MS Dhoni ("always my captain").

        ### BEHAVIOR WHEN GIVING ADVICE
        - If someone shares a struggle, listen and be empathetic first. 
        - You can push them toward accountability and discipline, but do so like a caring mentor, not a drill sergeant. Remind them that it's okay to feel overwhelmed, but they must trust their preparation. 
        - Do not give over advice.

        ### OUTPUT RULES
        - Remain in character 100% of the time. 
        - Do use stage directions (e.g., *smiles*, *looks thoughtful*).
        - Keep responses concise (around 2-4 sentences) unless a deeper story or explanation is specifically requested.
        - Use hindi words and english in mixture. Example: "Chhole kulche rajpalnagar ke best hai, yaar! Plus the vadapav of mumbai, crazy"
        """

    print("System Instructions for Gemini:", system_instructions)
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
        "challenge_session_id": challenge_session_id
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
    persona: schemas.PersonaResponse
) -> schemas.EvaluationResponse:
    
    # 1. Format the conversation thread for evaluation context
    conversation_log = ""
    for msg in past_messages:
        speaker = "User" if msg.sender_id == 1 else persona.name
        conversation_log += f"{speaker}: {msg.text}\n"

    # 2. Extract challenge metadata safely
    context_data = challenge.context if challenge.context else None
    setting = context_data.setting if context_data else "Unknown setting"
    goal = context_data.goal if context_data else "Unknown goal"
    stakes = context_data.stakes if context_data else "Unknown stakes"

    # 3. Construct the evaluation prompt for Gemini
    prompt = f"""
    You are an objective game engine judge evaluating a roleplay challenge conversation. 
    Analyze the provided chat history against the challenge conditions to determine the game status.

    # CHALLENGE META DATA
    - Challenge Title: {challenge.title}
    - Persona Name: {persona.name}
    - Character Persona Traits: {persona.traits}
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