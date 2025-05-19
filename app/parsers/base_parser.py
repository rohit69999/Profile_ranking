from abc import ABC, abstractmethod
from typing import Dict, Optional

class BaseParser(ABC):
    """Abstract base class for document parsers."""
    
    @abstractmethod
    def parse(self, file_path: str) -> Dict[str, Optional[str]]:
        """Parse document and return content with metadata."""
        pass