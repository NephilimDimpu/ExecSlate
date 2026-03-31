"""
ExecSlate Storage Service
Abstracts volatile data storage away from the relational database.
Currently implements LocalFileBackend (mimicking Amazon S3 object storage).
"""

import os
import gzip
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Base storage directory
STORAGE_ROOT = Path(__file__).parent / ".storage"

class StorageBackend:
    """Base interface for object storage."""
    def save(self, key: str, data: str) -> str:
        raise NotImplementedError
        
    def load(self, key: str) -> str:
        raise NotImplementedError

class LocalFileBackend(StorageBackend):
    """Local file system implementation simulating an S3 bucket."""
    
    def __init__(self):
        # Ensure the directory exists
        if not STORAGE_ROOT.exists():
            STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
            
    def _get_path(self, key: str) -> Path:
        # Sanitize key for local filesystem
        safe_key = key.replace("/", "_").replace("\\", "_")
        # Add .gz extension since we compress everything
        if not safe_key.endswith(".gz"):
            safe_key += ".gz"
        return STORAGE_ROOT / safe_key
        
    def save(self, key: str, data: str) -> str:
        """Saves data to a compressed local file. Returns the storage URI pointer."""
        if not data:
            return None
            
        file_path = self._get_path(key)
        try:
            # Compress data to save space, just like S3 optimized storage
            with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                f.write(data)
            return f"storage://{key}"
        except Exception as e:
            logger.error(f"Storage Service Error: Failed to save {key}: {e}")
            return None
            
    def load(self, uri: str) -> str:
        """Loads data from a compressed local file by its URI pointer."""
        if not uri or not uri.startswith("storage://"):
            return None
            
        key = uri.replace("storage://", "")
        file_path = self._get_path(key)
        
        if not file_path.exists():
            logger.warning(f"Storage Service Warning: Object missing {key}")
            return None
            
        try:
            with gzip.open(file_path, 'rt', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logger.error(f"Storage Service Error: Failed to load {key}: {e}")
            return None

# Singleton instance
storage = LocalFileBackend()
