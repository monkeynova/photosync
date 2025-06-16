"""
Photo metadata model for PhotoSync system
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict, field
from enum import Enum

class ProcessingState(Enum):
    """Photo processing states in the sync workflow"""
    DISCOVERED = "discovered"
    RESOLVED = "resolved"
    REPLICATED = "replicated"

class VisibilityLevel(Enum):
    """Canonical visibility levels"""
    PRIVATE = "private"
    FRIENDS = "friends"
    PUBLIC = "public"

class PhotoQuality(Enum):
    """Photo quality levels"""
    ORIGINAL = "original"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

@dataclass
class ServiceInstance:
    """Represents a photo instance on a specific service"""
    id: str  # Service-specific ID
    quality: PhotoQuality = PhotoQuality.ORIGINAL
    last_sync: Optional[datetime] = None
    url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "id": self.id,
            "quality": self.quality.value,
            "last_sync": self.last_sync.isoformat() if self.last_sync else None,
            "url": self.url
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ServiceInstance':
        """Create from dictionary"""
        return cls(
            id=data["id"],
            quality=PhotoQuality(data.get("quality", "original")),
            last_sync=datetime.fromisoformat(data["last_sync"]) if data.get("last_sync") else None,
            url=data.get("url")
        )

@dataclass
class Location:
    """Geographic location information"""
    lat: float
    lng: float
    address: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "lat": self.lat,
            "lng": self.lng,
            "address": self.address
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Location':
        return cls(
            lat=data["lat"],
            lng=data["lng"],
            address=data.get("address")
        )

@dataclass
class CameraInfo:
    """Camera/device information"""
    make: Optional[str] = None
    model: Optional[str] = None
    settings: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "make": self.make,
            "model": self.model,
            "settings": self.settings
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CameraInfo':
        return cls(
            make=data.get("make"),
            model=data.get("model"),
            settings=data.get("settings")
        )

@dataclass
class PhotoMetadata:
    """Core photo metadata extracted from EXIF and services"""
    taken_date: Optional[datetime] = None
    filename: Optional[str] = None
    location: Optional[Location] = None
    tags: List[str] = field(default_factory=list)
    caption: Optional[str] = None
    camera_info: Optional[CameraInfo] = None
    dimensions: Optional[Dict[str, int]] = None  # {"width": 1920, "height": 1080}
    file_size: Optional[int] = None  # bytes
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "taken_date": self.taken_date.isoformat() if self.taken_date else None,
            "filename": self.filename,
            "location": self.location.to_dict() if self.location else None,
            "tags": self.tags,
            "caption": self.caption,
            "camera_info": self.camera_info.to_dict() if self.camera_info else None,
            "dimensions": self.dimensions,
            "file_size": self.file_size
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhotoMetadata':
        return cls(
            taken_date=datetime.fromisoformat(data["taken_date"]) if data.get("taken_date") else None,
            filename=data.get("filename"),
            location=Location.from_dict(data["location"]) if data.get("location") else None,
            tags=data.get("tags", []),
            caption=data.get("caption"),
            camera_info=CameraInfo.from_dict(data["camera_info"]) if data.get("camera_info") else None,
            dimensions=data.get("dimensions"),
            file_size=data.get("file_size")
        )

@dataclass
class VisibilityDiscrepancy:
    """Tracks visibility mismatches between services"""
    service: str
    current: VisibilityLevel
    canonical: VisibilityLevel
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "service": self.service,
            "current": self.current.value,
            "canonical": self.canonical.value
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'VisibilityDiscrepancy':
        return cls(
            service=data["service"],
            current=VisibilityLevel(data["current"]),
            canonical=VisibilityLevel(data["canonical"])
        )

@dataclass
class PhotoVisibility:
    """Photo visibility settings across services"""
    canonical: VisibilityLevel = VisibilityLevel.PRIVATE
    per_service: Dict[str, VisibilityLevel] = field(default_factory=dict)
    discrepancies: List[VisibilityDiscrepancy] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "canonical": self.canonical.value,
            "per_service": {k: v.value for k, v in self.per_service.items()},
            "discrepancies": [d.to_dict() for d in self.discrepancies]
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhotoVisibility':
        return cls(
            canonical=VisibilityLevel(data.get("canonical", "private")),
            per_service={k: VisibilityLevel(v) for k, v in data.get("per_service", {}).items()},
            discrepancies=[VisibilityDiscrepancy.from_dict(d) for d in data.get("discrepancies", [])]
        )

@dataclass
class PhotoConflict:
    """Represents a conflict requiring manual resolution"""
    type: str  # e.g., "metadata_mismatch", "visibility_conflict", "duplicate_detected"
    description: str
    services: List[str]
    resolution_required: bool = True
    details: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "description": self.description,
            "services": self.services,
            "resolution_required": self.resolution_required,
            "details": self.details
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PhotoConflict':
        return cls(
            type=data["type"],
            description=data["description"],
            services=data["services"],
            resolution_required=data.get("resolution_required", True),
            details=data.get("details")
        )

class Photo:
    """
    Main photo entity representing a unique photo across all services.
    Follows the canonical photo model from the design document.
    """
    
    def __init__(self, 
                 photo_id: Optional[str] = None,
                 content_hash: Optional[str] = None,
                 canonical_source: Optional[str] = None,
                 source_of_truth_path: Optional[str] = None):
        
        self.photo_id = photo_id or str(uuid.uuid4())
        self.content_hash = content_hash
        self.canonical_source = canonical_source  # "service:service-id"
        self.source_of_truth_path = source_of_truth_path
        
        self.instances: Dict[str, ServiceInstance] = {}
        self.metadata = PhotoMetadata()
        self.visibility = PhotoVisibility()
        self.processing_state = ProcessingState.DISCOVERED
        self.conflicts: List[PhotoConflict] = []
        
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def add_service_instance(self, service_name: str, instance: ServiceInstance):
        """Add or update a service instance"""
        self.instances[service_name] = instance
        self.updated_at = datetime.now()
    
    def remove_service_instance(self, service_name: str):
        """Remove a service instance"""
        if service_name in self.instances:
            del self.instances[service_name]
            self.updated_at = datetime.now()
    
    def add_conflict(self, conflict: PhotoConflict):
        """Add a conflict requiring resolution"""
        self.conflicts.append(conflict)
        self.updated_at = datetime.now()
    
    def resolve_conflict(self, conflict_index: int):
        """Mark a conflict as resolved"""
        if 0 <= conflict_index < len(self.conflicts):
            self.conflicts[conflict_index].resolution_required = False
            self.updated_at = datetime.now()
    
    def has_unresolved_conflicts(self) -> bool:
        """Check if photo has unresolved conflicts"""
        return any(c.resolution_required for c in self.conflicts)
    
    def set_processing_state(self, state: ProcessingState):
        """Update processing state"""
        self.processing_state = state
        self.updated_at = datetime.now()
    
    def get_metadata_file_path(self, base_path: Path) -> Path:
        """Get the path where this photo's metadata should be stored"""
        # Organize by year based on taken_date or created_at
        date_for_organization = self.metadata.taken_date or self.created_at
        year = date_for_organization.year
        month = f"{date_for_organization.month:02d}"
        
        filename = f"{self.photo_id}.json"
        return base_path / "photos" / str(year) / month / filename
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return {
            "photo_id": self.photo_id,
            "content_hash": self.content_hash,
            "canonical_source": self.canonical_source,
            "source_of_truth_path": self.source_of_truth_path,
            "instances": {k: v.to_dict() for k, v in self.instances.items()},
            "metadata": self.metadata.to_dict(),
            "visibility": self.visibility.to_dict(),
            "processing_state": self.processing_state.value,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Photo':
        """Create Photo instance from dictionary"""
        photo = cls(
            photo_id=data.get("photo_id"),
            content_hash=data.get("content_hash"),
            canonical_source=data.get("canonical_source"),
            source_of_truth_path=data.get("source_of_truth_path")
        )
        
        # Load instances
        for service_name, instance_data in data.get("instances", {}).items():
            photo.instances[service_name] = ServiceInstance.from_dict(instance_data)
        
        # Load metadata
        if "metadata" in data:
            photo.metadata = PhotoMetadata.from_dict(data["metadata"])
        
        # Load visibility
        if "visibility" in data:
            photo.visibility = PhotoVisibility.from_dict(data["visibility"])
        
        # Load processing state
        if "processing_state" in data:
            photo.processing_state = ProcessingState(data["processing_state"])
        
        # Load conflicts
        photo.conflicts = [PhotoConflict.from_dict(c) for c in data.get("conflicts", [])]
        
        # Load timestamps
        if "created_at" in data:
            photo.created_at = datetime.fromisoformat(data["created_at"])
        if "updated_at" in data:
            photo.updated_at = datetime.fromisoformat(data["updated_at"])
        
        return photo
    
    def save_to_file(self, base_path: Path):
        """Save photo metadata to JSON file"""
        file_path = self.get_metadata_file_path(base_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(file_path, 'w') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
    
    @classmethod
    def load_from_file(cls, file_path: Path) -> 'Photo':
        """Load photo metadata from JSON file"""
        with open(file_path, 'r') as f:
            data = json.load(f)
        return cls.from_dict(data)
    
    def __str__(self) -> str:
        """String representation for debugging"""
        filename = self.metadata.filename or "unknown"
        services = list(self.instances.keys())
        return f"Photo({self.photo_id[:8]}...): {filename} on {services}"
    
    def __repr__(self) -> str:
        return f"Photo(photo_id='{self.photo_id}', services={list(self.instances.keys())})"
