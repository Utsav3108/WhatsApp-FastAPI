from typing import Protocol
from .context import BrainContext


class BrainComponent(Protocol):

    def update(self, context: BrainContext):
        pass

    def compile_prompt(self, context: BrainContext) -> str:
        pass