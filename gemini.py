from google import genai

client = genai.Client(api_key="AIzaSyC3UpAAI3A1f4NMzhzH2BayGJ-U0xvHrv4")

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


def ask_gemini(question):
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        config={
            "system_instruction": system_instructions
        },
        contents=f"Utsav: {question}"
    )

    MessageCreate = {
        "sender_id": 2, # Assuming 2 is the user_id for the AI persona
        "receiver_id": 1, # Assuming 1 is the user_id for Utsav
        "text": response.text,
    }

    return MessageCreate