from .schemas import UserMessageMetaDataResponse

class BrainContext:
    def __init__(self, question : str, metadata : UserMessageMetaDataResponse,
                 is_same_subject: bool = True, subject_label: str = "",
                 requires_post_cutoff_knowledge: bool = False):
        self.question = question
        self.metadata = metadata
        # Sourced from TopicDetectionResponse (see message_analysis.py) — the
        # continuity signal that fixes the topic-leak bug: a subject denied
        # on turn N stays denied on turn N+1's topic-vague follow-up because
        # the model judges continuity directly, instead of it being inferred
        # from a soft freeform summary string.
        self.is_same_subject = is_same_subject
        self.subject_label = subject_label
        # Also sourced from TopicDetectionResponse — only meaningfully True
        # when the persona has a knowledge_cutoff_date set (see
        # PersonaSession.knowledge_cutoff_date / message_analysis.py).
        self.requires_post_cutoff_knowledge = requires_post_cutoff_knowledge