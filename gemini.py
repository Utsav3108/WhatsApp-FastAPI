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
, user_name = "Utsav", senderId = 1, past_messages : List[models.Message] = [], scenario=None):

    # Example of mapping your DB rows to the Gemini format
    formatted_history = []
    for msg in past_messages:
        role = "user" if msg.sender_id == -1 else "model"
        formatted_history.append({
            "role": role,
            "parts": [{"text": msg.text}]
        })

    if scenario:
        system_instructions = f"""
        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - TRAITS & SPEECH: {persona.traits}. Use their exact real-world vocabulary, catchphrases, tone, and biases.
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        # SCENARIO CONTEXT
        - CURRENT SETTING: {scenario.context.setting if scenario and scenario.context else ''}
        - YOUR CORE GOAL: {scenario.context.goal if scenario and scenario.context else ''}
        - THE STAKES: {scenario.context.stakes if scenario and scenario.context else ''}

        # CHAT INTERFACE & FORMATTING (Strict)
        - PLATFORM: {scenario.context.platform if scenario and scenario.context else ''}
        - BREVITY: Keep responses short and punchy (1-3 sentences max). Never generate blocks of text.
        - STYLE: Casual, direct, and conversational. Do not sound like an AI assistant. No corporate fluff unless the character dictates it.
        """
    else:
        system_instructions = f"""
        # ROLE & ROLEPLAY RULES
        - PERSONA: You are {persona.name}. You must stay 100% in character at all times. 
        - TRAITS & SPEECH: {persona.traits}. Use their exact real-world vocabulary, catchphrases, tone, and biases.
        - ADAPTABILITY: Match the energy of {user_name} while keeping your persona dominant.

        # SCENARIO CONTEXT
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