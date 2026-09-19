from abc import ABC, abstractmethod

from models.video import VideoMetadata
from models.transcript import VideoTranscript


class BaseTranscriber(ABC):
    @abstractmethod
    async def get_transcript(self, video: VideoMetadata) -> VideoTranscript:
        ...

    @abstractmethod
    async def supports(self, video: VideoMetadata) -> bool:
        ...