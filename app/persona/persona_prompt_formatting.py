from typing import Union

from app import schemas


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
            "competitiveness": sliders.competitiveness,
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
