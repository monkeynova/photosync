"""
Google Photos Service Integration
"""

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional, Dict, Any, List
import uuid

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .base import BaseServiceAdapter
from ..models.photo import Photo, ServiceInstance, PhotoMetadata, PhotoQuality, VisibilityLevel, ProcessingState

logger = logging.getLogger(__name__)

# Original scope:
# SCOPES = ['https://www.googleapis.com/auth/photoslibrary.readonly']
# Broader scope for testing:
SCOPES = ['https://www.googleapis.com/auth/photoslibrary']
DEFAULT_TOKEN_FILE = "google_auth_token.json"

class GooglePhotosService(BaseServiceAdapter):
    """
    Service adapter for Google Photos.
    Handles authentication and fetching photo information.
    """
    def __init__(self, config: Dict[str, Any], metadata_repo_path: Path):
        super().__init__(config, metadata_repo_path)
        self.service_name = "google-photos"
        self.client_id = self.config.get("client_id")
        self.client_secret = self.config.get("client_secret")
        self.token_path = self.metadata_repo_path / "config" / self.config.get("token_file", DEFAULT_TOKEN_FILE)

        if not self.client_id or not self.client_secret:
            raise ValueError(f"Client ID and Client Secret must be configured for {self.service_name}")

    def _get_credentials(self) -> Optional[Credentials]:
        """
        Gets valid Google API credentials.
        Handles loading from token file, refreshing, or initiating new OAuth flow.
        """
        creds = None
        if self.token_path.exists():
            try:
                creds = Credentials.from_authorized_user_file(str(self.token_path), SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load token from {self.token_path}: {e}. Will attempt re-authentication.")
                creds = None # Ensure creds is None if loading fails

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    logger.info("Refreshing Google Photos API token.")
                    creds.refresh(Request())
                    if creds and creds.valid: # Log scopes after successful refresh
                        logger.info(f"Credentials refreshed successfully. Scopes: {creds.scopes}")
                except Exception as e:
                    logger.error(f"Failed to refresh token: {e}. Initiating new login.")
                    creds = None # Force new login
            else:
                logger.info("Initiating new Google Photos API login.")
                client_config = {
                    "installed": {
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                        "token_uri": "https://oauth2.googleapis.com/token",
                        "redirect_uris": ["http://localhost"] # Or "urn:ietf:wg:oauth:2.0:oob" for copy-paste code
                    }
                }
                flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
                # Try to run local server, fall back to console if it fails
                try:
                    creds = flow.run_local_server(port=0)
                except OSError: # Port might be in use or other issues
                     logger.warning("Failed to start local server for OAuth, falling back to console.")
                     creds = flow.run_console()

            if creds:
                try:
                    self.token_path.parent.mkdir(parents=True, exist_ok=True)
                    with open(self.token_path, 'w') as token_file:
                        token_file.write(creds.to_json())
                    logger.info(f"Google Photos API token saved to {self.token_path}. Scopes in new token: {creds.scopes}")
                except Exception as e:
                    logger.error(f"Failed to save token to {self.token_path}: {e}")
            else:
                logger.error("Failed to obtain Google Photos API credentials.")
                return None
        
        if creds and creds.valid: # Log scopes if loaded from file and valid
            logger.info(f"Using existing valid credentials. Scopes: {creds.scopes}")
            
        return creds

    def _parse_item_to_photo(self, item_data: Dict[str, Any]) -> Photo:
        """Converts a Google Photos MediaItem to a PhotoSync Photo object."""
        photo_id = str(uuid.uuid4()) # PhotoSync's internal ID
        photo = Photo(photo_id=photo_id)

        service_instance = ServiceInstance(
            id=item_data['id'],
            quality=PhotoQuality.ORIGINAL, # Assume original quality from API
            url=item_data.get('productUrl')
        )
        photo.add_service_instance(self.service_name, service_instance)
        photo.canonical_source = f"{self.service_name}:{item_data['id']}"

        # Populate metadata
        gphoto_meta = item_data.get('mediaMetadata', {})
        if gphoto_meta.get('creationTime'):
            photo.metadata.taken_date = datetime.fromisoformat(gphoto_meta['creationTime'].replace('Z', '+00:00'))
        
        photo.metadata.filename = item_data.get('filename')
        photo.metadata.caption = item_data.get('description') # Google Photos uses 'description' for caption

        if gphoto_meta.get('width') and gphoto_meta.get('height'):
            photo.metadata.dimensions = {
                "width": int(gphoto_meta['width']),
                "height": int(gphoto_meta['height'])
            }
        
        # Note: Google Photos API does not reliably provide detailed EXIF like GPS or full camera settings
        # for privacy reasons. This might need to be extracted after downloading the original file.
        # For now, we capture what's directly available.
        camera_meta = gphoto_meta.get('photo', {}) # 'photo' for still images, 'video' for videos
        if camera_meta:
            photo.metadata.camera_info = photo.metadata.camera_info or {} # Ensure CameraInfo is initialized if needed
            photo.metadata.camera_info.make = camera_meta.get('cameraMake')
            photo.metadata.camera_info.model = camera_meta.get('cameraModel')
            # Other fields like apertureFNumber, focalLength, isoEquivalent can be added if needed

        photo.set_processing_state(ProcessingState.DISCOVERED)
        photo.visibility.canonical = VisibilityLevel.PRIVATE # Default, can be refined later

        return photo

    def discover_photos(self, last_sync_time: Optional[datetime] = None) -> Iterator[Photo]:
        """
        Discover new or updated photos from Google Photos.
        Uses mediaItems.search with a date filter if last_sync_time is provided.
        Otherwise, lists all media items (can be very slow for large libraries).
        """
        creds = self._get_credentials()
        if not creds:
            logger.error(f"Cannot discover photos from {self.service_name}: No valid credentials.")
            return

        try:
            service = build('photoslibrary', 'v1', credentials=creds, static_discovery=False, cache_discovery=False)
            page_token = None
            
            search_body: Dict[str, Any] = {"pageSize": 100} # Max 100

            if last_sync_time:
                # Ensure last_sync_time is timezone-aware (UTC)
                if last_sync_time.tzinfo is None:
                    last_sync_time = last_sync_time.replace(tzinfo=timezone.utc)
                
                # Google Photos API expects date parts
                # We search for items created *after* the last sync time.
                # The API searches for items *within* the range.
                # For simplicity, we'll fetch items from last_sync_time up to now.
                # A more precise "modified since" is not directly supported for all changes.
                # 'creationTime' is the primary filterable date.
                now = datetime.now(timezone.utc)
                search_body["filters"] = {
                    "dateFilter": {
                        "ranges": [{
                            "startDate": {"year": last_sync_time.year, "month": last_sync_time.month, "day": last_sync_time.day},
                            "endDate": {"year": now.year, "month": now.month, "day": now.day}
                        }]
                    }
                }
                api_method = service.mediaItems().search
                request_kwargs = {'body': search_body}
            else:
                # List all items if no last_sync_time (can be very slow)
                logger.warning("No last_sync_time provided. Listing all media items from Google Photos. This may take a long time.")
                api_method = service.mediaItems().list
                request_kwargs = {'pageSize': 100}

            while True:
                if page_token:
                    if "body" in request_kwargs: # for search
                        request_kwargs["body"]["pageToken"] = page_token
                    else: # for list
                        request_kwargs["pageToken"] = page_token
                
                results = api_method(**request_kwargs).execute()
                items = results.get('mediaItems', [])
                
                for item_data in items:
                    yield self._parse_item_to_photo(item_data)

                page_token = results.get('nextPageToken')
                if not page_token:
                    break
        except HttpError as e:
            logger.error(f"Google Photos API error: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred during Google Photos discovery: {e}", exc_info=True)