"""
Photo Manager - Utilities for managing photo metadata collections
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Optional, Iterator, Set
from datetime import datetime

import jsonschema

from .photo import Photo, ProcessingState, PhotoConflict

logger = logging.getLogger(__name__)

class PhotoManager:
    """
    Manages a collection of photos in a metadata repository.
    Provides utilities for loading, saving, querying, and validating photos.
    """
    
    def __init__(self, metadata_repo_path: Path):
        self.metadata_repo_path = Path(metadata_repo_path)
        self.photos_dir = self.metadata_repo_path / "photos"
        self.schema_path = None  # Will be set when schema is loaded
        self._schema = None
        self._photo_cache: Dict[str, Photo] = {}
        
    def load_schema(self, schema_path: Optional[Path] = None) -> bool:
        """Load JSON schema for validation"""
        if schema_path:
            self.schema_path = schema_path
        else:
            # Try to find schema in package or repository
            possible_paths = [
                self.metadata_repo_path / "schemas" / "photo-metadata.schema.json",
                Path(__file__).parent.parent.parent / "schemas" / "photo-metadata.schema.json"
            ]
            
            for path in possible_paths:
                if path.exists():
                    self.schema_path = path
                    break
        
        if not self.schema_path or not self.schema_path.exists():
            logger.warning("Photo metadata schema not found - validation disabled")
            return False
        
        try:
            with open(self.schema_path) as f:
                self._schema = json.load(f)
            logger.info(f"Loaded photo metadata schema from {self.schema_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to load schema: {e}")
            return False
    
    def validate_photo(self, photo: Photo) -> List[str]:
        """
        Validate a photo against the JSON schema.
        Returns list of validation errors (empty if valid).
        """
        if not self._schema:
            return []  # Validation disabled
        
        try:
            jsonschema.validate(photo.to_dict(), self._schema)
            return []
        except jsonschema.ValidationError as e:
            return [str(e)]
        except Exception as e:
            return [f"Validation error: {e}"]
    
    def save_photo(self, photo: Photo, validate: bool = True) -> bool:
        """
        Save a photo to the metadata repository.
        Returns True if successful, False otherwise.
        """
        if validate:
            errors = self.validate_photo(photo)
            if errors:
                logger.error(f"Photo validation failed for {photo.photo_id}: {errors}")
                return False
        
        try:
            photo.save_to_file(self.metadata_repo_path)
            self._photo_cache[photo.photo_id] = photo
            logger.debug(f"Saved photo {photo.photo_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to save photo {photo.photo_id}: {e}")
            return False
    
    def load_photo(self, photo_id: str) -> Optional[Photo]:
        """Load a specific photo by ID"""
        if photo_id in self._photo_cache:
            return self._photo_cache[photo_id]
        
        # Search for the photo file
        for photo_file in self.photos_dir.rglob(f"{photo_id}.json"):
            try:
                photo = Photo.load_from_file(photo_file)
                self._photo_cache[photo_id] = photo
                return photo
            except Exception as e:
                logger.error(f"Failed to load photo from {photo_file}: {e}")
                return None
        
        return None
    
    def load_all_photos(self, use_cache: bool = True) -> List[Photo]:
        """Load all photos from the metadata repository"""
        if use_cache and self._photo_cache:
            return list(self._photo_cache.values())
        
        photos = []
        self._photo_cache.clear()
        
        if not self.photos_dir.exists():
            return photos
        
        for photo_file in self.photos_dir.rglob("*.json"):
            try:
                photo = Photo.load_from_file(photo_file)
                photos.append(photo)
                self._photo_cache[photo.photo_id] = photo
            except Exception as e:
                logger.error(f"Failed to load photo from {photo_file}: {e}")
        
        logger.info(f"Loaded {len(photos)} photos from metadata repository")
        return photos
    
    def get_photos_by_state(self, state: ProcessingState) -> List[Photo]:
        """Get all photos in a specific processing state"""
        photos = self.load_all_photos()
        return [p for p in photos if p.processing_state == state]
    
    def get_photos_with_conflicts(self) -> List[Photo]:
        """Get all photos with unresolved conflicts"""
        photos = self.load_all_photos()
        return [p for p in photos if p.has_unresolved_conflicts()]
    
    def get_photos_by_service(self, service_name: str) -> List[Photo]:
        """Get all photos that have instances on a specific service"""
        photos = self.load_all_photos()
        return [p for p in photos if service_name in p.instances]
    
    def get_photos_by_hash(self, content_hash: str) -> List[Photo]:
        """Get photos with matching content hash (for duplicate detection)"""
        photos = self.load_all_photos()
        return [p for p in photos if p.content_hash == content_hash]
    
    def get_photos_by_date_range(self, start_date: datetime, end_date: datetime) -> List[Photo]:
        """Get photos taken within a date range"""
        photos = self.load_all_photos()
        result = []
        
        for photo in photos:
            photo_date = photo.metadata.taken_date or photo.created_at
            if start_date <= photo_date <= end_date:
                result.append(photo)
        
        return result
    
    def get_statistics(self) -> Dict[str, any]:
        """Get statistics about the photo collection"""
        photos = self.load_all_photos()
        
        stats = {
            "total_photos": len(photos),
            "by_state": {},
            "by_service": {},
            "with_conflicts": 0,
            "with_location": 0,
            "by_year": {}
        }
        
        # Count by processing state
        for state in ProcessingState:
            stats["by_state"][state.value] = len([p for p in photos if p.processing_state == state])
        
        # Count by service
        all_services = set()
        for photo in photos:
            all_services.update(photo.instances.keys())
        
        for service in all_services:
            stats["by_service"][service] = len([p for p in photos if service in p.instances])
        
        # Count conflicts and location data
        for photo in photos:
            if photo.has_unresolved_conflicts():
                stats["with_conflicts"] += 1
            if photo.metadata.location:
                stats["with_location"] += 1
            
            # Count by year
            photo_date = photo.metadata.taken_date or photo.created_at
            year = photo_date.year
            stats["by_year"][year] = stats["by_year"].get(year, 0) + 1
        
        return stats
    
    def find_duplicates(self) -> Dict[str, List[Photo]]:
        """
        Find potential duplicate photos based on content hash.
        Returns dict mapping content_hash to list of photos with that hash.
        """
        photos = self.load_all_photos()
        hash_to_photos = {}
        
        for photo in photos:
            if photo.content_hash:
                if photo.content_hash not in hash_to_photos:
                    hash_to_photos[photo.content_hash] = []
                hash_to_photos[photo.content_hash].append(photo)
        
        # Return only hashes with multiple photos
        return {h: photos for h, photos in hash_to_photos.items() if len(photos) > 1}
    
    def cleanup_cache(self):
        """Clear the photo cache to free memory"""
        self._photo_cache.clear()
    
    def ensure_directories(self):
        """Ensure the required directory structure exists"""
        directories = [
            self.photos_dir,
            self.photos_dir / "2024",
            self.photos_dir / "2023",
        ]
        
        for directory in directories:
            directory.mkdir(parents=True, exist_ok=True)
    
    def get_photo_file_path(self, photo_id: str) -> Optional[Path]:
        """Get the file path for a photo's metadata file"""
        for photo_file in self.photos_dir.rglob(f"{photo_id}.json"):
            return photo_file
        return None
    
    def delete_photo(self, photo_id: str) -> bool:
        """Delete a photo's metadata file and remove it from the cache.
        Returns True if successful, False otherwise.
        """
        photo_file_path = self.get_photo_file_path(photo_id)
        
        if photo_file_path and photo_file_path.exists():
            try:
                photo_file_path.unlink()
                logger.info(f"Deleted photo metadata file: {photo_file_path}")
                if photo_id in self._photo_cache:
                    del self._photo_cache[photo_id]
                    logger.debug(f"Removed photo {photo_id} from cache.")
                return True
            except Exception as e:
                logger.error(f"Error deleting photo file {photo_file_path}: {e}")
                return False
        else:
            logger.warning(f"Photo metadata file for {photo_id} not found. Cannot delete.")
            return False