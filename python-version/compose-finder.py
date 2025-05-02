#!/usr/bin/env python3
# Docker Compose Finder Script
# Creates symlinks to docker-compose files found on the system

import os
import re
import sys
import hashlib
import subprocess
from pathlib import Path
from typing import List, Dict, Set


# Configuration variables
SYMLINK_DIR = "/opt/image-updater/docker-compose-finder/compose-links"

# Exclude list - Docker Compose files you don't want to add to symlink folder
EXCLUDED_FILES = [
    "/example/excluded/file.yml"
]

# List where you want to look for compose files (Space separated)
SEARCH_DIRECTORIES = ["/opt", "/etc", "/home/your_username_here"]


def create_hash(filepath: str, length: int = 8) -> str:
    """Create a short hash of a filepath."""
    return hashlib.sha1(filepath.encode()).hexdigest()[:length]


def find_docker_compose_files(directories: List[str]) -> List[str]:
    """Find all docker-compose files in the given directories."""
    compose_files = []
    
    for directory in directories:
        if not os.path.isdir(directory):
            print(f"Warning: Directory {directory} does not exist, skipping")
            continue
            
        try:
            # Use find command for efficiency (similar to bash script)
            cmd = [
                "find", directory, 
                "-type", "f", 
                "(",
                "-iname", "*docker-compose*.yml",
                "-o",
                "-iname", "*docker-compose*.yaml",
                ")",
                "2>/dev/null"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0 and result.stdout:
                # Add each file to our list
                for line in result.stdout.splitlines():
                    if line.strip():
                        compose_files.append(line.strip())
        except Exception as e:
            print(f"Error searching {directory}: {e}")
    
    return compose_files


def is_excluded(filepath: str, excluded_files: List[str]) -> bool:
    """Check if a file is in the exclusion list."""
    # Get real path to handle any symlinks
    real_path = os.path.realpath(filepath)
    return real_path in excluded_files


def update_symlinks():
    """Main function to update the symlinks."""
    # Create the symlink directory if it doesn't exist
    os.makedirs(SYMLINK_DIR, exist_ok=True)
    
    # Find all docker-compose-related files
    docker_compose_files = find_docker_compose_files(SEARCH_DIRECTORIES)
    print(f"Found {len(docker_compose_files)} Docker Compose files")
    
    # Clear out duplicate name tracking
    used_names = {}
    
    # Process each file found
    for compose_file in docker_compose_files:
        # If in exclusion list, remove corresponding symlink if it exists
        if is_excluded(compose_file, EXCLUDED_FILES):
            basename = os.path.basename(compose_file)
            file_hash = create_hash(compose_file)
            
            # Handle both naming conventions (with and without hash)
            base_without_ext = os.path.splitext(basename)[0]
            if base_without_ext.endswith('.yml'):
                alt_base = f"{base_without_ext[:-4]}-{file_hash}.yml"
            else:
                alt_base = f"{base_without_ext}-{file_hash}.yml"
            
            # Try both naming variants
            for symlink_name in [basename, alt_base]:
                symlink_path = os.path.join(SYMLINK_DIR, symlink_name)
                if os.path.islink(symlink_path):
                    print(f"Removing symlink for excluded file: {symlink_path}")
                    os.remove(symlink_path)
            continue
        
        # Build symlink name
        basename = os.path.basename(compose_file)
        if basename in used_names:
            # Create a unique name using hash if basename already used
            file_hash = create_hash(compose_file)
            base_without_ext, ext = os.path.splitext(basename)
            symlink_name = f"{base_without_ext}-{file_hash}{ext}"
        else:
            symlink_name = basename
            used_names[basename] = 1
        
        symlink_path = os.path.join(SYMLINK_DIR, symlink_name)
        
        # Create or refresh symlink
        if os.path.islink(symlink_path):
            try:
                existing_target = os.path.realpath(symlink_path)
                if existing_target == compose_file:
                    print(f"Symlink already correct: {symlink_path}")
                    continue
            except FileNotFoundError:
                # Broken symlink
                pass
            
        # Create or update the symlink
        print(f"Creating symlink for {compose_file}")
        # Remove existing symlink if it exists
        if os.path.islink(symlink_path):
            os.remove(symlink_path)
        os.symlink(compose_file, symlink_path)
    
    # Remove symlinks pointing to deleted files
    for entry in os.listdir(SYMLINK_DIR):
        existing_symlink = os.path.join(SYMLINK_DIR, entry)
        if os.path.islink(existing_symlink):
            try:
                target_path = os.path.realpath(existing_symlink)
                if not os.path.isfile(target_path):
                    print(f"Removing dead symlink: {existing_symlink}")
                    os.remove(existing_symlink)
            except FileNotFoundError:
                # This is a broken symlink
                print(f"Removing broken symlink: {existing_symlink}")
                os.remove(existing_symlink)
    
    print("Symlink folder has been updated.")


if __name__ == "__main__":
    update_symlinks()
