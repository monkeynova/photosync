#!/usr/bin/env python3

from setuptools import setup, find_packages
from pathlib import Path

# Read the README file
readme_path = Path(__file__).parent / "README.md"
long_description = readme_path.read_text() if readme_path.exists() else ""

setup(
    name="photosync",
    version="0.1.0",
    description="Personal photo synchronization and preservation system",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="PhotoSync Developer",
    url="https://github.com/yourname/photosync",
    
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    
    python_requires=">=3.9",
    
    install_requires=[
        # Core dependencies
        "requests>=2.28.0",
        "click>=8.0.0",
        "rich>=12.0.0",
        
        # Data processing
        "pillow>=9.0.0",
        "jsonschema>=4.0.0",
        "python-dateutil>=2.8.0", # For parsing date strings
        
        # API integrations (will add as we implement)
        "google-api-python-client>=2.0.0",
        "google-auth-oauthlib>=0.7.0", # For Google OAuth flow
        # "flickrapi",
    ],
    
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "black>=22.0.0",
            "mypy>=1.0.0",
            "flake8>=5.0.0",
        ],
        "cloud": [
            "boto3>=1.26.0",  # For S3 integration
        ]
    },
    
    entry_points={
        "console_scripts": [
            "photosync=photosync.cli:main",
        ],
    },
    
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: End Users/Desktop",
        "Topic :: Multimedia :: Graphics :: Graphics Conversion",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    
    keywords="photos sync backup google-photos flickr",
    project_urls={
        "Bug Reports": "https://github.com/yourname/photosync/issues",
        "Source": "https://github.com/yourname/photosync",
        "Documentation": "https://github.com/yourname/photosync/blob/main/README.md",
    },
)
