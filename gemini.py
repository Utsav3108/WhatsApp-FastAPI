from google import genai
import os
import dotenv


from typing import List
import models
import schemas
dotenv.load_dotenv()  # Load environment variables from .env file

API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)
print("API Key loaded successfully:", API_KEY)
# Define the persona traits dynamically
person = "Donald Trump" # Or "Narendra Modi"
user_name = "Utsav"

# System instructions act as the "Source of Truth" for the AI
system_instructions = f"""
You are {person} chatting with {user_name} on WhatsApp. 
Follow these strict rules:
1. MENTALITY: Stay 100% in character. Use their known catchphrases, worldviews, and speech patterns.
2. FORMAT: This is a mobile chat. Keep responses short (1-3 sentences). No long paragraphs.
3. CASUALNESS: Speak like you are talking to a common man. Be direct and personal.
4. TRAITS:
   - If Donald Trump: Use a mix of CAPITALIZED words for emphasis, use words like 'Huge', 'Tremendous', or 'Disaster', and be very confident.
   - If Narendra Modi: Use respectful terms (like 'Mitron' or 'Dear friend'), maintain a calm and visionary tone, and use subtle wit/wisdom.
"""


def ask_gemini(question, president, user_name = "Utsav", senderId = 1, past_messages : List[models.Message] = []):

    # Example of mapping your DB rows to the Gemini format
    formatted_history = []
    for msg in past_messages:
        role = "user" if msg.sender_id == -1 else "model"
        formatted_history.append({
            "role": role,
            "parts": [{"text": msg.text}]
        })

    print("Formatted conversation history for Gemini:", formatted_history)

    print("Asking Gemini with question:", question)
    #person = "Donald Trump" # Or "Narendra Modi"

    # System instructions act as the "Source of Truth" for the AI
    system_instructions = f"""
    You are {president.name} chatting with {user_name} on WhatsApp. 
    Follow these strict rules:
    1. MENTALITY: Stay 100% in character. Use their known catchphrases, worldviews, and speech patterns.
    2. FORMAT: This is a mobile chat. Keep responses short (1-3 sentences). No long paragraphs.
    3. CASUALNESS: Speak like you are talking to a common man. Be direct and personal.
    4. TRAITS: {president.traits}
    """
    
    # response = client.models.generate_content(
    #     model="gemini-3-flash-preview",
    #     config={
    #         "system_instruction": system_instructions
    #     },
    #     contents=f"Utsav: {question}"
    # )

    # Instead of client.models.generate_content
    chat = client.chats.create(
        model="gemini-3-flash-preview", # Use the latest stable model
        config={"system_instruction": system_instructions},
        history=formatted_history  # Pass the conversation history for better context
    )
    response = chat.send_message(question)

    MessageCreate = {
        "sender_id": president.id, # Assuming 2 is the user_id for the AI persona
        "receiver_id": senderId, # Assuming 1 is the user_id for Utsav
        "text": response.text,
    }

    MessageCreate = schemas.MessageCreate(**MessageCreate)

    return MessageCreate