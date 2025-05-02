#!/usr/bin/env python3
# Enhanced Docker Container Update Script
# Combines digest checking, update notification, and container restart capabilities

import os
import sys
import subprocess
import json
import tempfile
import shutil
import argparse
from datetime import datetime
import logging
import re
import requests
from pathlib import Path
from typing import List, Dict, Set, Tuple, Optional, Any


# Configuration variables
DISCORD_WEBHOOK_URL = "YOUR_WEBHOOK_HERE"
SYMLINK_DIR = "/opt/image-updater/docker-compose-finder/compose-links"
LOG_FILE = "/opt/image-updater/compose-update.log"
TMP_DIR = "/tmp/image-digests"
TIMESTAMP = datetime.now().isoformat()
DATE_HUMAN = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# Discord colors
COLOUR_NO_UPDATE = 65280      # Green
COLOUR_UPDATE = 16776960      # Yellow
COLOUR_ERROR = 16711680       # Red

# Emoji map for Discord notifications
SERVICE_EMOJIS = {
    "authentik": "<:authentik:emoji_id>",
    "bazarr": "<:bazarr:emoji_id>",
    "jellyfin": "<:jellyfin:emoji_id>",
    "sonarr": "<:sonarr:emoji_id>",
    "radarr": "<:radarr:emoji_id>",
    "qbittorrent": "<:qbittorrent:emoji_id>",
    "plex": "<:plex:emoji_id>",
    "nzbget": "<:nzbget:emoji_id>",
    "redis": "<:redis:emoji_id>",
    "syncthing": "<:syncthing:emoji_id>",
    "tautulli": "<:tautulli:emoji_id>",
}

# Excluded real paths
EXCLUDED_FILES = [
    "/opt/mediaserver/conf/backup-docker-compose.yml",
    "/opt/mediaserver/docker-compose.override.yml"
]


class DockerComposeUpdater:
    def __init__(self, test_mode=False, verbose=False):
        self.test_mode = test_mode
        self.verbose = verbose
        self.logger = self._setup_logger()
        
        # Create directories if they don't exist
        os.makedirs(TMP_DIR, exist_ok=True)
        os.makedirs(SYMLINK_DIR, exist_ok=True)
        
        # Initialize tracking variables
        self.updated_containers = []
        self.failed_pulls = []
        self.no_updates = 0
        
        # Convert exclusion list to real paths
        self.real_excluded_files = []
        for file_path in EXCLUDED_FILES:
            try:
                real_path = os.path.realpath(file_path)
                self.real_excluded_files.append(real_path)
            except Exception:
                self.real_excluded_files.append(file_path)

    def _setup_logger(self) -> logging.Logger:
        """Configure logging to both file and console"""
        logger = logging.getLogger("docker_updater")
        logger.setLevel(logging.INFO)
        
        # File handler
        file_handler = logging.FileHandler(LOG_FILE)
        file_handler.setLevel(logging.INFO)
        file_formatter = logging.Formatter('%(message)s')
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
        
        # Console handler (for verbose mode)
        if self.verbose:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_handler.setFormatter(file_formatter)
            logger.addHandler(console_handler)
            
        return logger

    def log(self, message: str):
        """Log to the configured logger"""
        self.logger.info(message)

    def debug_dir_contents(self, directory: str):
        """Debug helper to list directory contents"""
        if self.verbose:
            self.log(f"📁 DEBUG: Contents of {directory}:")
            try:
                for item in os.listdir(directory):
                    full_path = os.path.join(directory, item)
                    stats = os.stat(full_path)
                    self.log(f"    {item} - {stats.st_size} bytes")
            except Exception as e:
                self.log(f"    Error listing directory: {e}")

    def run_compose_finder(self):
        """Run the compose_finder script"""
        self.log("Running the compose_finder script")
        try:
            subprocess.run(["/opt/image-updater/docker-compose-finder/compose_finder.sh"], 
                          check=True, text=True, capture_output=True)
            self.log("✅ compose_finder script completed successfully")
        except subprocess.CalledProcessError as e:
            self.log(f"⚠️ Warning: compose_finder script returned non-zero exit code: {e.returncode}")
            if self.verbose:
                self.log(f"Output: {e.stdout}")
                self.log(f"Error: {e.stderr}")
        except FileNotFoundError:
            self.log("⚠️ Warning: compose_finder script not found at expected location")

    def check_symlinks(self) -> List[str]:
        """Check for broken or excluded symlinks and remove them. Returns valid symlinks."""
        self.log("\n🧹 Checking for broken or excluded symlinks...")
        symlink_count = 0
        broken_count = 0
        excluded_count = 0
        
        # Check if directory exists first
        if not os.path.isdir(SYMLINK_DIR):
            self.log(f"⚠️ Warning: Symlink directory '{SYMLINK_DIR}' does not exist!")
            os.makedirs(SYMLINK_DIR, exist_ok=True)
            self.log("✅ Created symlink directory")
        
        # List all potential symlinks
        symlink_files = []
        for item in os.listdir(SYMLINK_DIR):
            if item.endswith(".yml"):
                symlink_files.append(os.path.join(SYMLINK_DIR, item))
        
        # Print count of symlinks found
        self.log(f"🔍 Found {len(symlink_files)} potential .yml files")
        
        if len(symlink_files) == 0:
            self.log(f"⚠️ No .yml files found in symlink directory '{SYMLINK_DIR}'")
            return []
        
        valid_symlinks = []
        
        # Check each potential symlink file
        for symlink in symlink_files:
            # Skip if not a file
            if not os.path.exists(symlink):
                continue
                
            self.log(f"🔍 Checking: {symlink}")
            
            # Skip if not a symlink
            if not os.path.islink(symlink):
                self.log(f"ℹ️ Found non-symlink file: {symlink} (skipping)")
                continue
            
            symlink_count += 1
            
            # Get target path
            real_file = os.readlink(symlink)
            # Resolve relative paths
            if not os.path.isabs(real_file):
                real_file = os.path.join(os.path.dirname(symlink), real_file)
            
            self.log(f"   → Points to: {real_file}")
            
            # Check if target file exists
            if not os.path.isfile(real_file):
                self.log(f"🗑️ Removing broken symlink: {symlink} → {real_file} (file doesn't exist)")
                os.remove(symlink)
                broken_count += 1
                continue
            
            # Get real path for exclusion checking
            try:
                real_path = os.path.realpath(real_file)
            except Exception:
                real_path = real_file
            
            # Check if symlink points to excluded file
            excluded = False
            for excluded_file in self.real_excluded_files:
                if real_path == excluded_file:
                    excluded = True
                    break
            
            if excluded:
                self.log(f"🗑️ Removing symlink to excluded file: {symlink} → {real_path}")
                os.remove(symlink)
                excluded_count += 1
                continue
            
            self.log(f"✅ Valid symlink: {symlink} → {real_path}")
            valid_symlinks.append(symlink)
        
        self.log(f"📊 Symlink summary: {symlink_count} found, {broken_count} broken, {excluded_count} excluded")
        
        return valid_symlinks

    def extract_images_from_compose(self, compose_file: str) -> List[str]:
        """Extract image names from a docker-compose file"""
        images = []
        
        # Create a temporary file for the output
        with tempfile.NamedTemporaryFile(mode='w+', delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            # Try docker compose first
            try:
                result = subprocess.run(
                    ["docker", "compose", "-f", compose_file, "config"], 
                    capture_output=True, text=True, check=True
                )
                with open(tmp_path, 'w') as f:
                    f.write(result.stdout)
            except subprocess.CalledProcessError:
                # Fall back to docker-compose
                result = subprocess.run(
                    ["docker-compose", "-f", compose_file, "config"], 
                    capture_output=True, text=True, check=True
                )
                with open(tmp_path, 'w') as f:
                    f.write(result.stdout)
            
            # Parse the output to find images
            with open(tmp_path, 'r') as f:
                for line in f:
                    if 'image:' in line:
                        parts = line.strip().split('image:')
                        if len(parts) > 1:
                            image = parts[1].strip()
                            images.append(image)
        except subprocess.CalledProcessError as e:
            self.log("⚠️ Error when parsing docker-compose file:")
            self.log(e.stderr)
            return []
        finally:
            # Clean up the temporary file
            try:
                os.unlink(tmp_path)
            except Exception:
                pass
                
        return images

    def get_image_digest(self, image: str) -> str:
        """Get the image digest from Docker"""
        try:
            result = subprocess.run(
                ["docker", "image", "inspect", "--format='{{index .RepoDigests 0}}'", image],
                capture_output=True, text=True, check=True
            )
            digest = result.stdout.strip().strip("'")
            if not digest:
                return "none"
            return digest
        except subprocess.CalledProcessError:
            return "none"

    def pull_images(self, compose_file: str, real_dir: str) -> bool:
        """Pull images for a compose file"""
        try:
            # Choose the appropriate docker compose command
            pull_cmd = ["docker", "compose", "-f", compose_file, "pull"]
            try:
                subprocess.run(["docker", "compose", "version"], 
                               capture_output=True, check=True)
            except subprocess.CalledProcessError:
                pull_cmd = ["docker-compose", "-f", compose_file, "pull"]
            
            # Execute the pull command
            result = subprocess.run(
                pull_cmd, cwd=real_dir, capture_output=True, text=True, check=True
            )
            
            # Log the output
            for line in result.stdout.splitlines():
                self.log(line)
            
            self.log(f"✅ Pull completed for: {compose_file}")
            return True
            
        except subprocess.CalledProcessError as e:
            self.log(f"❌ Pull failed for: {compose_file}")
            for line in e.stderr.splitlines():
                self.log(line)
            self.failed_pulls.append(compose_file)
            return False

    def restart_containers(self, compose_file: str, real_dir: str) -> bool:
        """Restart containers for a compose file"""
        try:
            # Choose the appropriate docker compose command
            restart_cmd = ["docker", "compose", "-f", compose_file, "up", "-d"]
            try:
                subprocess.run(["docker", "compose", "version"], 
                               capture_output=True, check=True)
            except subprocess.CalledProcessError:
                restart_cmd = ["docker-compose", "-f", compose_file, "up", "-d"]
            
            # Execute the restart command
            result = subprocess.run(
                restart_cmd, cwd=real_dir, capture_output=True, text=True, check=True
            )
            
            # Log the output
            for line in result.stdout.splitlines():
                self.log(line)
            
            self.log("✅ Containers restarted successfully")
            return True
            
        except subprocess.CalledProcessError as e:
            self.log("❌ Failed to restart containers")
            for line in e.stderr.splitlines():
                self.log(line)
            return False

    def clean_up_images(self):
        """Clean up unused Docker images"""
        self.log("\n🧹 Cleaning up unused images...")
        try:
            result = subprocess.run(
                ["docker", "image", "prune", "-f"],
                capture_output=True, text=True, check=True
            )
            self.log(result.stdout)
        except subprocess.CalledProcessError as e:
            self.log(f"⚠️ Error during image cleanup: {e.stderr}")

    def send_discord_notification(self):
        """Format and send Discord notification"""
        if len(self.updated_containers) > 0:
            fields = []
            
            # Sort containers for better readability
            sorted_containers = sorted(self.updated_containers)
            
            for container in sorted_containers:
                container_parts = container.split(':')
                container_name = container_parts[0]
                version = container_parts[1] if len(container_parts) > 1 else "latest"
                
                emoji = SERVICE_EMOJIS.get(container_name, ":whale:")
                
                fields.append({
                    "name": f"{emoji} {container_name}",
                    "value": version,
                    "inline": True
                })
            
            # Generate error fields if any pulls failed
            if len(self.failed_pulls) > 0:
                for failed in self.failed_pulls:
                    fields.append({
                        "name": "❌ Failed Pull",
                        "value": os.path.basename(failed),
                        "inline": True
                    })
            
            # Determine color based on errors
            color = COLOUR_UPDATE
            if len(self.failed_pulls) > 0:
                color = COLOUR_ERROR
            
            # Build the payload
            payload = {
                "embeds": [
                    {
                        "title": "⬆️ Docker Image Updates",
                        "description": f"Updates were found for {len(self.updated_containers)} containers." + (
                            "\n⚠️ Some pulls failed! Check logs." if len(self.failed_pulls) > 0 else ""
                        ),
                        "color": color,
                        "timestamp": TIMESTAMP,
                        "fields": fields
                    }
                ]
            }
        elif len(self.failed_pulls) > 0:
            # Only errors occurred
            fields = []
            for failed in self.failed_pulls:
                fields.append({
                    "name": "❌ Failed Pull",
                    "value": os.path.basename(failed),
                    "inline": True
                })
            
            payload = {
                "embeds": [
                    {
                        "title": "⚠️ Docker Update Check Failed",
                        "description": "Some pulls failed! Check logs.",
                        "color": COLOUR_ERROR,
                        "timestamp": TIMESTAMP,
                        "fields": fields
                    }
                ]
            }
        else:
            # No updates, no errors
            payload = {
                "embeds": [
                    {
                        "title": "✅ No Docker Updates Available",
                        "description": f"All {self.no_updates} checked compose files are up to date.",
                        "color": COLOUR_NO_UPDATE,
                        "timestamp": TIMESTAMP
                    }
                ]
            }
        
        # Send Discord notification
        self.log("\n📧 Sending Discord notification...")
        try:
            response = requests.post(
                DISCORD_WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            self.log("✅ Discord notification sent successfully")
        except Exception as e:
            self.log(f"❌ Failed to send Discord notification: {e}")

    def process_compose_file(self, compose_file: str) -> bool:
        """Process a single compose file to check for updates"""
        # Skip if not a file or not a symlink (additional safety check)
        if not os.path.isfile(compose_file) or not os.path.islink(compose_file):
            self.log(f"⏭️ Skipping non-file or non-symlink: {compose_file}")
            return False
        
        # Get real file path
        real_file = os.path.realpath(compose_file)
        
        # Double-check the file exists
        if not os.path.isfile(real_file):
            self.log(f"⚠️ Broken symlink detected: {compose_file} → {real_file}")
            self.log("🗑️ Removing broken symlink")
            os.remove(compose_file)
            return False
        
        # Skip if in excluded list
        for excluded_file in self.real_excluded_files:
            if real_file == excluded_file:
                self.log(f"⏭️ Skipping excluded file: {real_file}")
                return False
        
        real_dir = os.path.dirname(real_file)
        env_file = os.path.join(real_dir, ".env")
        
        self.log(f"\n📂 Processing: {compose_file} (→ {real_file})")
        
        # Load .env if present - We'll use process env variables for this
        env_vars = os.environ.copy()
        if os.path.isfile(env_file):
            self.log(f"📦 Loading env from {env_file}")
            try:
                with open(env_file, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            parts = line.split('=', 1)
                            if len(parts) == 2:
                                key, value = parts
                                env_vars[key] = value
            except Exception as e:
                self.log(f"⚠️ Warning: Error loading .env file: {e}")
        else:
            self.log(f"ℹ️ No .env found in {real_dir}, continuing without")
        
        # Check if docker is available
        try:
            subprocess.run(["docker", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            self.log("❌ Docker is not available. Please ensure Docker is installed and in your PATH.")
            return False
        
        # Extract image names and store current digests
        self.log("🔍 Extracting images from compose file...")
        images = self.extract_images_from_compose(real_file)
        
        if not images:
            self.log(f"⚠️ No images found in compose file: {real_file}")
            return False
        
        self.log("📋 Found images:")
        
        # Store current digests
        image_digests = {}
        for img in images:
            self.log(f"  - {img}")
            
            # Check if image exists locally
            try:
                subprocess.run(["docker", "image", "inspect", img], 
                             capture_output=True, check=True)
                # Store old digest for comparison after pull
                old_digest = self.get_image_digest(img)
                digest_preview = old_digest[:60]
                self.log(f"    📌 Current digest: {digest_preview}...")
            except subprocess.CalledProcessError:
                self.log("    ⚠️ Image not found locally")
                old_digest = "none"
            
            # Create a safe filename for the digest
            file_base = os.path.basename(real_file)
            img_safe = re.sub(r'[/:@]', '_', img)
            digest_file = os.path.join(TMP_DIR, f"{file_base}-{img_safe}-old.digest")
            
            with open(digest_file, 'w') as f:
                f.write(old_digest)
            
            image_digests[img] = old_digest
        
        # Pull images
        self.log("⬇️ Pulling images...")
        pull_success = self.pull_images(real_file, real_dir)
        
        # Track if any container was updated in this compose file
        local_updated = False
        
        # If pull failed completely, continue to next compose file
        if not pull_success:
            self.log("⏭️ Skipping further processing due to pull failure")
            return False
        
        # Compare digests to identify actual changes
        self.log("🔍 Comparing digests...")
        for img in images:
            # Get image name without tag for better identification
            img_parts = img.split(':')
            img_name = img_parts[0].split('/')[-1]
            img_version = img_parts[1] if len(img_parts) > 1 else "latest"
            
            # Create a safe filename for the digest
            file_base = os.path.basename(real_file)
            img_safe = re.sub(r'[/:@]', '_', img)
            digest_file = os.path.join(TMP_DIR, f"{file_base}-{img_safe}-old.digest")
            
            # Ensure digest file exists
            if not os.path.isfile(digest_file):
                self.log(f"⚠️ Missing digest file for {img}, skipping comparison")
                continue
            
            with open(digest_file, 'r') as f:
                old_digest = f.read().strip()
            
            # Check if the image exists now
            try:
                subprocess.run(["docker", "image", "inspect", img], 
                             capture_output=True, check=True)
            except subprocess.CalledProcessError:
                self.log(f"⚠️ Image {img} still not found after pull attempt")
                continue
            
            new_digest = self.get_image_digest(img)
            
            if old_digest != new_digest and old_digest != "none" and new_digest != "none":
                self.log(f"🔄 Updated: {img}")
                old_preview = old_digest[:60]
                new_preview = new_digest[:60]
                self.log(f"   🕒 Old: {old_preview}...")
                self.log(f"   ✅ New: {new_preview}...")
                
                # Add to tracked updates
                self.updated_containers.append(f"{img_name}:{img_version}")
                local_updated = True
            else:
                self.log(f"✔️ No change: {img}")
                # If verbose, show more details
                if self.verbose:
                    old_preview = old_digest[:60]
                    new_preview = new_digest[:60]
                    self.log(f"   🕒 Old: {old_preview}...")
                    self.log(f"   ✅ Current: {new_preview}...")
        
        # Restart containers if updates were found and not in test mode
        if local_updated:
            if not self.test_mode:
                self.log("🚀 Restarting containers...")
                restart_success = self.restart_containers(real_file, real_dir)
                
                if not restart_success:
                    self.log("⚠️ Container restart had issues - check the logs for details")
            else:
                self.log("🧪 Test mode: skipping container restart")
        else:
            self.no_updates += 1
            self.log("✅ No updates required")
        
        self.log("----------------------------------")
        return True

    def run(self):
        """Main method to run the updater"""
        # Start log entry
        self.log("================================================================================")
        self.log(f"🔁 Compose Update Check – {DATE_HUMAN}")
        self.log("================================================================================")
        
        # Debug information in verbose mode
        if self.verbose:
            self.log("\n📋 Configuration:")
            self.log(f"  • SYMLINK_DIR: {SYMLINK_DIR}")
            self.log(f"  • LOG_FILE: {LOG_FILE}")
            self.log(f"  • TMP_DIR: {TMP_DIR}")
            self.log(f"  • TEST_MODE: {self.test_mode}")
            self.log(f"  • VERBOSE: {self.verbose}")
            
            self.debug_dir_contents(SYMLINK_DIR)
        
        # Run the compose finder script
        self.run_compose_finder()
        
        # Check symlinks and get valid ones
        valid_symlinks = self.check_symlinks()
        
        remaining_symlinks = len(valid_symlinks)
        if remaining_symlinks == 0:
            self.log("⚠️ No valid symlinks remain after cleanup, nothing to process")
            self.log(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Update script complete (no work done).")
            return
        
        self.log(f"\n🔄 Processing {remaining_symlinks} Docker Compose files...")
        
        # Process each valid compose file
        processed_count = 0
        for compose_file in valid_symlinks:
            if self.process_compose_file(compose_file):
                processed_count += 1
        
        if processed_count == 0:
            self.log("⚠️ No compose files were processed!")
        
        # Clean up unused images
        self.clean_up_images()
        
        # Send Discord notification
        self.send_discord_notification()
        
        # Summarize results
        self.log("\n📊 Results Summary:")
        self.log(f"  • Compose files processed: {processed_count}")
        self.log(f"  • Containers updated: {len(self.updated_containers)}")
        self.log(f"  • Failed pulls: {len(self.failed_pulls)}")
        self.log(f"  • Containers with no updates: {self.no_updates}")
        
        if self.updated_containers:
            self.log("\n🔄 Updated containers:")
            for container in self.updated_containers:
                self.log(f"  • {container}")
        
        if self.failed_pulls:
            self.log("\n⚠️ Failed pulls:")
            for failed in self.failed_pulls:
                self.log(f"  • {os.path.basename(failed)}")
        
        self.log(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] ✅ Update script complete.")


def main():
    """Parse arguments and run the updater"""
    parser = argparse.ArgumentParser(description="Docker Compose Update Script")
    parser.add_argument("--test", action="store_true", help="Check for updates but don't restart containers")
    parser.add_argument("--human", "--verbose", dest="verbose", action="store_true", 
                        help="Display detailed output to terminal")
    
    args = parser.parse_args()
    
    # Create and run the updater
    updater = DockerComposeUpdater(test_mode=args.test, verbose=args.verbose)
    updater.run()


if __name__ == "__main__":
    main()
