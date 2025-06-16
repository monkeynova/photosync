"""
Base classes for service integrations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Iterator, Optional, Dict, Any
from datetime import datetime
from pathlib import Path

from ..models.photo import Photo

logger = logging.getLogger(__name__)


class BaseServiceAdapter(ABC):
    """Abstract base class for photo service adapters."""

    def __init__(self, config: Dict[str, Any], metadata_repo_path: Path):
        self.config = config
        self.metadata_repo_path = metadata_repo_path
        self.service_name = "unknown_service" # Should be overridden by subclasses

    @abstractmethod
    def discover_photos(self, last_sync_time: Optional[datetime] = None) -> Iterator[Photo]:
        """
        Discover new or updated photos from the service.
        Yields Photo objects.
        """
        pass