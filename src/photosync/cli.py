#!/usr/bin/env python3
"""
PhotoSync CLI - Personal photo synchronization and preservation system
"""

import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime
import logging

class PhotoSyncCLI:
    def __init__(self):
        self.metadata_repo_path = self._detect_metadata_repo()
        self.setup_logging()
    
    def _detect_metadata_repo(self):
        """
        Detect metadata repository path based on how CLI is executed.
        If run as ./bin/photosync, metadata repo is parent directory.
        Otherwise, require --metadata-repo argument.
        """
        current_path = Path.cwd()
        cli_path = Path(__file__).resolve()
        
        # Check if we're in a bin/ directory within a metadata repo
        if cli_path.parent.name == 'bin' and (cli_path.parent.parent / 'config').exists():
            return cli_path.parent.parent
        
        # Check if current directory looks like a metadata repo
        if (current_path / 'config').exists() and (current_path / 'photos').exists():
            return current_path
            
        return None
    
    def setup_logging(self):
        """Setup logging configuration"""
        log_level = os.getenv('PHOTOSYNC_LOG_LEVEL', 'INFO')
        logging.basicConfig(
            level=getattr(logging, log_level.upper()),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        self.logger = logging.getLogger('photosync')
    
    def init_metadata_repo(self, path=None):
        """Initialize a new metadata repository structure"""
        if path:
            repo_path = Path(path).resolve()
        else:
            repo_path = Path.cwd()
        
        print(f"Initializing metadata repository at: {repo_path}")
        
        # Create directory structure
        directories = [
            'photos/2024', 'photos/2023',
            'config',
            'blobs/2024', 'blobs/2023', 
            'logs',
            'bin'
        ]
        
        for dir_path in directories:
            full_path = repo_path / dir_path
            full_path.mkdir(parents=True, exist_ok=True)
            print(f"  Created: {dir_path}")
        
        # Create .gitkeep files for empty directories
        gitkeep_dirs = ['blobs/2024', 'blobs/2023', 'logs']
        for dir_path in gitkeep_dirs:
            gitkeep_file = repo_path / dir_path / '.gitkeep'
            gitkeep_file.touch()
        
        # Create initial configuration files
        self._create_initial_configs(repo_path)
        
        # Create .gitignore
        gitignore_content = """# Ignore actual photo blobs (too large for git)
blobs/**/*.jpg
blobs/**/*.jpeg
blobs/**/*.png
blobs/**/*.tiff
blobs/**/*.raw

# Ignore logs
logs/*.log

# Ignore sensitive config with API keys
config/services.json

# Keep directory structure
!blobs/*/.gitkeep
!logs/.gitkeep
"""
        gitignore_path = repo_path / '.gitignore'
        gitignore_path.write_text(gitignore_content)
        print(f"  Created: .gitignore")
        
        print(f"\nMetadata repository initialized successfully!")
        print(f"Next steps:")
        print(f"  1. Edit config/services.json with your API credentials")
        print(f"  2. Run: photosync status")
        
        return repo_path
    
    def _create_initial_configs(self, repo_path):
        """Create initial configuration files"""
        
        # services.json template
        services_config = {
            "google-photos": {
                "enabled": False,
                "client_id": "your-google-client-id",
                "client_secret": "your-google-client-secret",
                "rate_limit": {"requests_per_minute": 1000}
            },
            "flickr": {
                "enabled": False,
                "api_key": "your-flickr-api-key",
                "api_secret": "your-flickr-api-secret",
                "rate_limit": {"requests_per_hour": 3600}
            }
        }
        
        services_path = repo_path / 'config' / 'services.json.template'
        services_path.write_text(json.dumps(services_config, indent=2))
        print(f"  Created: config/services.json.template")
        
        # user-preferences.json
        preferences_config = {
            "default_visibility": "private",
            "auto_resolve": ["exact_duplicates", "quality_variants"],
            "blob_storage": {
                "primary": "local",
                "local_path": "./blobs",
                "s3_bucket": None,
                "b2_bucket": None
            },
            "sync_preferences": {
                "download_originals": True,
                "max_parallel_downloads": 5,
                "incremental_sync_days": 30
            }
        }
        
        preferences_path = repo_path / 'config' / 'user-preferences.json'
        preferences_path.write_text(json.dumps(preferences_config, indent=2))
        print(f"  Created: config/user-preferences.json")
        
        # sync-state.json (empty initially)
        sync_state = {
            "last_sync": None,
            "total_photos": 0,
            "services": {},
            "last_discovery": None,
            "pending_conflicts": 0
        }
        
        sync_state_path = repo_path / 'config' / 'sync-state.json'
        sync_state_path.write_text(json.dumps(sync_state, indent=2))
        print(f"  Created: config/sync-state.json")
    
    def show_status(self):
        """Show current status of the photo sync system"""
        if not self.metadata_repo_path:
            print("❌ No metadata repository found")
            print("Run 'photosync init' to create one, or cd to an existing metadata repository")
            return
        
        print(f"📁 Metadata Repository: {self.metadata_repo_path}")
        
        # Check configuration
        config_status = self._check_configuration()
        print(f"\n⚙️  Configuration Status:")
        for item in config_status:
            print(f"  {item}")
        
        # Check photo statistics
        photo_stats = self._get_photo_statistics()
        print(f"\n📊 Photo Statistics:")
        for stat in photo_stats:
            print(f"  {stat}")
        
        # Check sync state
        sync_info = self._get_sync_info()
        print(f"\n🔄 Sync Information:")
        for info in sync_info:
            print(f"  {info}")
    
    def _check_configuration(self):
        """Check configuration status"""
        status = []
        
        config_dir = self.metadata_repo_path / 'config'
        
        # Check if services.json exists (not template)
        services_file = config_dir / 'services.json'
        if services_file.exists():
            status.append("✅ services.json configured")
            try:
                with open(services_file) as f:
                    services = json.load(f)
                enabled_services = [name for name, config in services.items() if config.get('enabled', False)]
                if enabled_services:
                    status.append(f"   📡 Enabled services: {', '.join(enabled_services)}")
                else:
                    status.append("   ⚠️  No services enabled")
            except Exception as e:
                status.append(f"   ❌ Error reading services.json: {e}")
        else:
            status.append("⚠️  services.json not found (copy from template and configure)")
        
        # Check preferences
        prefs_file = config_dir / 'user-preferences.json'
        if prefs_file.exists():
            status.append("✅ user-preferences.json exists")
        else:
            status.append("❌ user-preferences.json missing")
            
        return status
    
    def _get_photo_statistics(self):
        """Get photo statistics from metadata"""
        stats = []
        
        photos_dir = self.metadata_repo_path / 'photos'
        if not photos_dir.exists():
            stats.append("❌ Photos directory not found")
            return stats
        
        # Count metadata files
        total_photos = len(list(photos_dir.rglob('*.json')))
        stats.append(f"📸 Total photos in metadata: {total_photos}")
        
        if total_photos > 0:
            # Count by year
            for year_dir in sorted(photos_dir.iterdir()):
                if year_dir.is_dir():
                    year_count = len(list(year_dir.rglob('*.json')))
                    stats.append(f"   {year_dir.name}: {year_count} photos")
        
        # Check blob storage
        blobs_dir = self.metadata_repo_path / 'blobs'
        if blobs_dir.exists():
            blob_files = list(blobs_dir.rglob('*.jpg')) + list(blobs_dir.rglob('*.jpeg')) + list(blobs_dir.rglob('*.png'))
            stats.append(f"💾 Blob files stored locally: {len(blob_files)}")
        
        return stats
    
    def _get_sync_info(self):
        """Get sync state information"""
        info = []
        
        sync_state_file = self.metadata_repo_path / 'config' / 'sync-state.json'
        if not sync_state_file.exists():
            info.append("❌ Sync state file not found")
            return info
        
        try:
            with open(sync_state_file) as f:
                sync_state = json.load(f)
            
            last_sync = sync_state.get('last_sync')
            if last_sync:
                info.append(f"🕐 Last sync: {last_sync}")
            else:
                info.append("🕐 Never synced")
            
            last_discovery = sync_state.get('last_discovery')
            if last_discovery:
                info.append(f"🔍 Last discovery: {last_discovery}")
            
            pending_conflicts = sync_state.get('pending_conflicts', 0)
            if pending_conflicts > 0:
                info.append(f"⚠️  Pending conflicts: {pending_conflicts}")
            else:
                info.append("✅ No pending conflicts")
                
        except Exception as e:
            info.append(f"❌ Error reading sync state: {e}")
        
        return info

def main():
    parser = argparse.ArgumentParser(
        description='PhotoSync - Personal photo synchronization and preservation system',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  photosync init                    # Initialize metadata repository in current directory
  photosync init /path/to/repo      # Initialize metadata repository at specific path
  photosync status                  # Show current status
  photosync --metadata-repo /path   # Specify metadata repository path
        """
    )
    
    parser.add_argument('--metadata-repo', 
                       help='Path to metadata repository (auto-detected if not specified)')
    parser.add_argument('--version', action='version', version='PhotoSync 0.1.0')
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Init command
    init_parser = subparsers.add_parser('init', help='Initialize metadata repository')
    init_parser.add_argument('path', nargs='?', help='Path for new metadata repository (default: current directory)')
    
    # Status command
    status_parser = subparsers.add_parser('status', help='Show current status')
    
    args = parser.parse_args()
    
    # Handle --metadata-repo override
    cli = PhotoSyncCLI()
    if args.metadata_repo:
        cli.metadata_repo_path = Path(args.metadata_repo).resolve()
    
    # Execute commands
    if args.command == 'init':
        cli.init_metadata_repo(args.path)
    elif args.command == 'status':
        cli.show_status()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
