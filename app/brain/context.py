from .schemas import UserMessageMetaDataResponse

class BrainContext:
    def __init__(self, question : str, metadata : UserMessageMetaDataResponse):
        self.question = question
        self.metadata = metadata