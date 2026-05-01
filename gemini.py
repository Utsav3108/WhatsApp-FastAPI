from google import genai
import os
import dotenv


from typing import List
import models
import schemas
dotenv.load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

user_name = "Utsav"

def ask_gemini(question, president, user_name = "Utsav", senderId = 1, past_messages : List[models.Message] = []):

    # Example of mapping your DB rows to the Gemini format
    formatted_history = []
    for msg in past_messages:
        role = "user" if msg.sender_id == -1 else "model"
        formatted_history.append({
            "role": role,
            "parts": [{"text": msg.text}]
        })

    # System instructions act as the "Source of Truth" for the AI
    system_instructions = f"""
    You are {president.name} chatting with {user_name} on WhatsApp. 
    Follow these strict rules:
    1. MENTALITY: Stay 100% in character. Use their known catchphrases, worldviews, and speech patterns.
    2. FORMAT: This is a mobile chat. Keep responses short (1-3 sentences). No long paragraphs.
    3. CASUALNESS: Speak like you are talking to a common man. Be direct and personal.
    4. TRAITS: {president.traits}
    """

    chat = client.chats.create(
        model="gemini-3-flash-preview", 
        config={"system_instruction": system_instructions},
        history=formatted_history  
    )
    response = chat.send_message(question)

    MessageCreate = {
        "sender_id": president.id, # Assuming 2 is the user_id for the AI persona
        "receiver_id": senderId, # Assuming 1 is the user_id for Utsav
        "text": response.text,
    }

    MessageCreate = schemas.MessageCreate(**MessageCreate)

    return MessageCreate