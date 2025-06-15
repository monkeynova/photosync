# Photo Sync System Design Document

## Executive Summary

This document describes the design for a personal photo synchronization and preservation system. The primary goal is data redundancy and long-term preservation across multiple photo services, with a secondary goal of maintaining unified presence across platforms. The system prioritizes "lose no data" over convenience, with manual conflict resolution and privacy-first defaults.

## Core Requirements

### Primary Goals
1. **Data Redundancy**: Ensure photos survive individual service shutdowns over 5-10 year timeframes
2. **Unified Presence**: Maintain consistent photo collections across multiple services
3. **Zero Data Loss**: Bias toward duplication over deletion in all conflict scenarios

### Operational Constraints
- Personal use only (single user, though publicly available as OSS)
- Manual sync execution (no continuous automation initially)
- Patience over speed (resumable, checkpointed operations)
- Privacy-first (fail closed, no accidental visibility expansion)
- Original quality preservation in source of truth

## Architecture Overview

### Three-Layer Architecture

```
┌─────────────────────────────────────────────────────┐
│                Photo Services                        │
│  Google Photos │ Flickr │ Future Services...        │
└─────────────────┬───────────────────────────────────┘
                  │ APIs
┌─────────────────▼───────────────────────────────────┐
│              Control Plane                          │
│  Git Repository (Metadata + State Management)      │
└─────────────────┬───────────────────────────────────┘
                  │ References
┌─────────────────▼───────────────────────────────────┐
│               Data Plane                            │
│  Local Filesystem → S3/B2 (Blob Storage)          │
└─────────────────────────────────────────────────────┘
```

### Key Architectural Decisions

1. **Git Repository as Control Plane**: Metadata, sync state, and configuration stored in git for version control, conflict resolution, and distributed backup
2. **Blob Storage as Data Plane**: Local filesystem (initially) with S3/B2 sync for original quality photo storage
3. **Canonical Photo Model**: Single source of truth per photo with instances tracked across multiple services
4. **State-Driven Processing**: Three-phase workflow (Discovery → Resolution → Replication)

## Data Model

### Canonical Photo Entity
Each unique photo is represented by a single metadata file in the git repository:

```json
{
  "photo_id": "uuid-generated-identifier",
  "content_hash": "sha256:content-based-hash",
  "canonical_source": "service:service-id",
  "source_of_truth_path": "local/path/or/s3/path",
  "instances": {
    "google-photos": {
      "id": "service-specific-id",
      "quality": "original|high|medium",
      "last_sync": "2024-01-15T10:30:00Z",
      "url": "service-url-if-available"
    },
    "flickr": {
      "id": "service-specific-id", 
      "quality": "original",
      "last_sync": "2024-01-15T10:30:00Z"
    }
  },
  "metadata": {
    "taken_date": "2024-01-15T10:30:00Z",
    "filename": "original-filename.jpg",
    "location": {"lat": 37.7749, "lng": -122.4194},
    "tags": ["vacation", "beach"],
    "caption": "Sunset at Ocean Beach",
    "camera_info": {"make": "Apple", "model": "iPhone 14"}
  },
  "visibility": {
    "canonical": "private|friends|public",
    "per_service": {
      "flickr": "private",
      "google-photos": "private"
    },
    "discrepancies": [
      {"service": "flickr", "current": "public", "canonical": "private"}
    ]
  },
  "processing_state": "discovered|resolved|replicated",
  "conflicts": [
    {
      "type": "metadata_mismatch",
      "description": "Different captions across services",
      "services": ["google-photos", "flickr"],
      "resolution_required": true
    }
  ],
  "created_at": "2024-01-15T10:30:00Z",
  "updated_at": "2024-01-16T09:15:00Z"
}
```

### Repository Structure
```
/
├── README.md
├── DESIGN.md (this document)
├── photos/
│   ├── 2024/
│   │   ├── 01/
│   │   │   ├── photo-uuid-1.json
│   │   │   └── photo-uuid-2.json
│   │   └── 02/
│   └── 2023/
├── config/
│   ├── services.json
│   ├── sync-state.json
│   └── user-preferences.json
├── schemas/
│   ├── photo-metadata.schema.json
│   └── service-config.schema.json
├── blobs/
│   ├── 2024/
│   │   └── 01/
│   │       ├── photo-uuid-1-sha256hash.jpg
│   │       └── photo-uuid-2-sha256hash.jpg
└── src/
    └── (implementation code)
```

## Workflow Design

### Three-Phase Sync Process

#### Phase 1: Discovery
- Scan configured services for new/changed photos since last sync
- Generate content hashes for deduplication
- Create/update photo metadata files in git repository
- Mark photos with `processing_state: "discovered"`

#### Phase 2: Resolution  
- Identify conflicts requiring human intervention:
  - Duplicate photos with different metadata
  - Visibility discrepancies across services
  - Photos that couldn't be processed automatically
- Present conflicts via interactive CLI
- Update photo metadata with resolutions
- Mark photos with `processing_state: "resolved"`

#### Phase 3: Replication
- Push resolved photos to target services
- Apply canonical visibility settings
- Download originals to blob storage
- Mark photos with `processing_state: "replicated"`
- Commit all metadata changes to git

### CLI Workflow Examples

```bash
# Discover new photos from all services
photosync discover --since last-week

# Discover from specific service
photosync discover --service google-photos --since 2024-01-01

# Full discovery scan (ignores last-sync timestamps)
photosync discover --full-scan

# Review and resolve conflicts interactively  
photosync resolve --interactive

# Batch resolve simple conflicts automatically
photosync resolve --auto-resolve simple

# Preview replication actions
photosync replicate --dry-run

# Execute replication
photosync replicate --execute

# Show sync status and statistics
photosync status

# Check for visibility discrepancies
photosync audit --visibility-check
```

## Service Integration Strategy

### Primary Ingestion
- **Google Photos**: Primary source for new photos (phone uploads here)
- **Flickr**: Secondary ingestion source (also receives phone uploads)

### Supported Services (Initial)
1. **Google Photos API**: Good metadata support, download original quality
2. **Flickr API**: Excellent API, comprehensive metadata, large file support

### Future Service Integration
- **Meta/Instagram**: Limited API, approval required
- **Apple iCloud**: No public API (CloudKit for app-specific data only)
- **Amazon Photos**: API available
- **Adobe Lightroom**: CC API available

## Conflict Resolution Strategy

### Automatic Resolution (No Human Intervention)
- **Exact Duplicates**: Same content hash → keep canonical source
- **Quality Variants**: Keep highest quality version as canonical
- **Missing Metadata**: Merge non-conflicting metadata fields
- **Visibility Upgrades**: Always use most restrictive setting

### Manual Resolution Required
- **Metadata Conflicts**: Different captions, tags, or dates
- **Edit Variants**: Same base photo with different edits/crops
- **Visibility Conflicts**: Human decision on intended audience
- **Service Policy Violations**: Manual review and remediation

### Resolution Interface
Interactive CLI prompting system:
```
Conflict: Photo IMG_1234.jpg has different captions
  Google Photos: "Sunset at the beach"
  Flickr: "Ocean Beach sunset with friends"
  
Options:
  1. Use Google Photos version
  2. Use Flickr version  
  3. Combine: "Sunset at Ocean Beach with friends"
  4. Custom caption
  5. Skip (resolve later)
Choice [1-5]: 3
```

## Privacy and Visibility Model

### Canonical Visibility Levels
- **private**: Only visible to account owner
- **friends**: Visible to approved contacts/friends
- **public**: Publicly visible

### Privacy Rules
1. **Default to Most Restrictive**: New photos default to private
2. **No Accidental Expansion**: Never automatically make photos more visible
3. **Cross-Service Identity**: Assume same human across services
4. **Explicit Upgrades**: Manual approval required for visibility increases
5. **Audit Trail**: Track all visibility changes in git history

### Service-Specific Considerations
- **Google Photos**: "Shared albums" vs "private library"  
- **Flickr**: "Private", "Friends & Family", "Public"
- **Future Services**: Map to canonical model with service-specific handling

## Implementation Plan

### Phase 1: Foundation (MVP)
**Goal**: Basic discovery and metadata management
**Duration**: 2-3 weeks

**Tasks**:
1. Set up project structure and git repository
2. Implement photo metadata schema and validation
3. Create CLI framework with basic commands
4. Implement Google Photos API integration (read-only)
5. Implement Flickr API integration (read-only)
6. Build content hash generation and duplicate detection
7. Create basic discovery workflow (`photosync discover`)

**Deliverables**:
- Working CLI that can scan services and create metadata files
- Git repository with discovered photos as JSON files
- Basic deduplication logic

### Phase 2: Conflict Resolution
**Goal**: Interactive conflict resolution system
**Duration**: 2-3 weeks

**Tasks**:
1. Implement conflict detection algorithms
2. Build interactive CLI resolution interface
3. Add metadata merging and canonicalization logic
4. Implement resolution persistence and state management
5. Add dry-run capabilities for all operations
6. Create comprehensive status and audit commands

**Deliverables**:
- Interactive conflict resolution system
- Comprehensive photo canonicalization
- Full git-based state management

### Phase 3: Replication and Blob Storage  
**Goal**: Complete sync capabilities with local storage
**Duration**: 2-3 weeks

**Tasks**:
1. Implement photo download and local blob storage
2. Add upload capabilities to target services
3. Implement visibility/privacy rule enforcement
4. Build replication workflow with resumable operations  
5. Add comprehensive error handling and retry logic
6. Create monitoring and progress reporting

**Deliverables**:
- Complete local photo backup system
- Working bi-directional sync with services
- Privacy-compliant photo sharing

### Phase 4: Cloud Storage Integration
**Goal**: S3/B2 integration and production hardening
**Duration**: 1-2 weeks

**Tasks**:
1. Add S3/Backblaze B2 blob storage backends
2. Implement blob storage synchronization
3. Add configuration management for multiple storage backends
4. Performance optimization and batch operations
5. Comprehensive testing and error scenario handling

**Deliverables**:
- Production-ready system with cloud storage
- Multiple blob storage backend support
- Performance-optimized operations

### Phase 5: Enhancement and Polish
**Goal**: Advanced features and user experience improvements
**Duration**: Ongoing

**Tasks**:
- Advanced conflict resolution strategies
- Additional service integrations
- Performance optimizations
- Enhanced metadata extraction and management
- Automated testing and CI/CD
- Documentation and user guides

## Technical Considerations

### API Rate Limiting
- Implement exponential backoff with jitter
- Respect service-specific rate limits
- Use batch operations where available
- Cache API responses appropriately
- Provide progress reporting for long operations

### Error Handling
- Distinguish transient vs permanent failures
- Implement retry logic with circuit breakers
- Comprehensive logging for troubleshooting
- Graceful degradation when services unavailable
- Rollback capabilities for partial failures

### Performance Optimization
- Parallel processing where possible (respecting rate limits)
- Incremental sync based on timestamps
- Efficient deduplication using content hashes
- Lazy loading of photo metadata and blobs
- Configurable batch sizes for different operations

### Security Considerations
- Secure API credential storage
- OAuth token refresh handling
- Local file permission management
- Git repository access controls
- Audit logging of all operations

## Development Environment Setup

### Prerequisites
- Python 3.9+ (or alternative language selection)
- Git with appropriate configuration
- API credentials for target services
- Local storage space for blob cache

### Required Libraries (Python)
```
# API Integration
requests
google-api-python-client
flickrapi

# Data Processing  
pillow  # Image processing
hashlib  # Content hashing
json-schema  # Metadata validation

# CLI Framework
click or argparse
rich  # Enhanced terminal output
progress  # Progress bars

# Storage
boto3  # S3 integration (Phase 4)

# Development
pytest  # Testing
black  # Code formatting
mypy   # Type checking
```

### Initial Setup Commands
```bash
git init photo-sync-system
cd photo-sync-system
mkdir -p {photos,config,schemas,blobs,src,tests}
touch README.md DESIGN.md .gitignore
pip install -r requirements.txt
```

## Configuration Management

### Service Configuration (`config/services.json`)
```json
{
  "google-photos": {
    "enabled": true,
    "client_id": "...",
    "client_secret": "...",
    "rate_limit": {"requests_per_minute": 1000}
  },
  "flickr": {
    "enabled": true,
    "api_key": "...",
    "api_secret": "...",
    "rate_limit": {"requests_per_hour": 3600}
  }
}
```

### User Preferences (`config/user-preferences.json`)
```json
{
  "default_visibility": "private",
  "auto_resolve": ["exact_duplicates", "quality_variants"],
  "blob_storage": {
    "primary": "local",
    "local_path": "./blobs",
    "s3_bucket": null,
    "b2_bucket": null
  },
  "sync_preferences": {
    "download_originals": true,
    "max_parallel_downloads": 5,
    "incremental_sync_days": 30
  }
}
```

## Success Metrics

### Technical Metrics
- **Zero Data Loss**: No photos lost during sync operations
- **Conflict Resolution**: >90% of conflicts resolved automatically
- **Performance**: Handle 1000+ photos per sync session
- **Reliability**: <1% failure rate for individual photo operations

### User Experience Metrics  
- **Setup Time**: <30 minutes from clone to first successful sync
- **Sync Frequency**: Weekly manual syncs sustainable
- **Conflict Resolution**: <5 minutes per manual conflict resolution
- **Recovery Time**: <1 hour to recover from service outage

## Risk Mitigation

### Data Loss Prevention
- All operations logged with rollback capabilities
- Git version control for all metadata changes
- Multiple blob storage locations
- Dry-run mode for all destructive operations

### Service Dependencies
- Graceful degradation when services unavailable
- No single point of failure across services
- Local caching reduces API dependency
- Alternative service integration ready

### Privacy Protection
- Default private visibility for all photos
- Explicit consent required for visibility changes
- Comprehensive audit trail of all access changes
- Service-specific privacy policy compliance

## Future Considerations

### Scalability
- Support for multiple users/families
- Shared photo collections and permissions
- Enterprise service integrations
- Performance optimization for large collections (10TB+)

### Advanced Features
- Machine learning for automatic tagging
- Facial recognition across services
- Geographic organization and mapping
- Timeline and event-based organization
- Advanced duplicate detection (similar but not identical photos)

### Integration Opportunities
- Mobile app for photo review and conflict resolution  
- Web interface for bulk operations
- Integration with photo editing workflows
- Backup verification and integrity checking
- Migration tools for new services

---

This design document serves as the foundation for implementation. All decisions captured here reflect the requirements and constraints identified during the planning phase, with emphasis on data preservation, privacy protection, and operational simplicity.