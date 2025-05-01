#!/bin/bash
# Enhanced Docker Container Update Script
# Combines digest checking, update notification, and container restart capabilities

# Enable error handling but with safer defaults
set -uo pipefail
# Note: Not using -e to prevent premature exits

# Function to log to file and optionally to stdout
log() {
  echo -e "$1" >> "$LOG_FILE"
  if [[ "$VERBOSE" == "true" ]]; then
    echo -e "$1"
  fi
}

# Function to debug directory contents - helpful in verbose mode
debug_dir_contents() {
  if [[ "$VERBOSE" == "true" ]]; then
    local dir=$1
    log "📁 DEBUG: Contents of $dir:"
    ls -la "$dir" | while read -r line; do
      log "    $line"
    done
  fi
}

# Configuration variables
DISCORD_WEBHOOK_URL="YOUR_WEBHOOK_HERE"
SYMLINK_DIR="/opt/image-updater/compose-links"
LOG_FILE="/opt/image-updater/compose-update.log"
TMP_DIR="/tmp/image-digests"
TIMESTAMP=$(date --iso-8601=seconds)
DATE_HUMAN=$(date "+%Y-%m-%d %H:%M:%S")
VERBOSE="false"

# Default configuration
TEST_MODE="false"

# Process command line arguments
while [[ $# -gt 0 ]]; do
  key="$1"
  case $key in
    --test)
      TEST_MODE="true"
      shift
      ;;
    --human|--verbose)
      VERBOSE="true"
      shift
      ;;
    --help)
      echo "Usage: $0 [options]"
      echo "Options:"
      echo "  --test        Check for updates but don't restart containers"
      echo "  --human       Display detailed output to terminal (same as --verbose)"
      echo "  --verbose     Display detailed output to terminal (same as --human)"
      echo "  --help        Display this help message"
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      echo "Run '$0 --help' for usage information"
      exit 1
      ;;
  esac
done

# Discord colors
COLOUR_NO_UPDATE=65280      # Green
COLOUR_UPDATE=16776960      # Yellow
COLOUR_ERROR=16711680       # Red

# Emoji map for Discord notifications
declare -A SERVICE_EMOJIS
SERVICE_EMOJIS=(
  ["bazarr"]="<:bazarr:emoji_id_here>"
  ["jellyfin"]="<:jellyfin:emoji_id_here>"
  ["sonarr"]="<:sonarr:emoji_id_here>"
  ["radarr"]="<:radarr:emoji_id_here>"
  ["qbittorrent"]="<:qbittorrent:emoji_id_here>"
  ["plex"]="<:plex:emoji_id_here>"
  ["nzbget"]="<:nzbget:emoji_id_here>"
  ["redis"]="<:redis:emoji_id_here>"
  ["syncthing"]="<:syncthing:emoji_id_here>"
  ["tautulli"]="<:tautulli:emoji_id_here>"
)

# Initialize arrays to track container updates
UPDATED_CONTAINERS=()
FAILED_PULLS=()
NO_UPDATES=0


echo "Running the compose_finder script"
/path/to/compose_finder.sh
# Excluded real paths
EXCLUDED_FILES=(
  "/opt/mediaserver/conf/backup-docker-compose.yml"
  "/opt/mediaserver/docker-compose.override.yml"
)

# Create directories if they don't exist
mkdir -p "$TMP_DIR"

# Start log entry
log "================================================================================"
log "🔁 Compose Update Check – $DATE_HUMAN"
log "================================================================================"

# Debug information in verbose mode
if [[ "$VERBOSE" == "true" ]]; then
  log "\n📋 Configuration:"
  log "  • SYMLINK_DIR: $SYMLINK_DIR"
  log "  • LOG_FILE: $LOG_FILE"
  log "  • TMP_DIR: $TMP_DIR"
  log "  • TEST_MODE: $TEST_MODE"
  log "  • VERBOSE: $VERBOSE"
  
  debug_dir_contents "$SYMLINK_DIR"
fi

# Convert exclusion list to real paths
REAL_EXCLUDED_FILES=()
for file in "${EXCLUDED_FILES[@]}"; do
  REAL_EXCLUDED_FILES+=( "$(readlink -f "$file" 2>/dev/null || echo "$file")" )
done

# Check for broken or excluded symlinks and remove them
log "\n🧹 Checking for broken or excluded symlinks..."
symlink_count=0
broken_count=0
excluded_count=0

# Check if directory exists first
if [[ ! -d "$SYMLINK_DIR" ]]; then
  log "⚠️  Warning: Symlink directory '$SYMLINK_DIR' does not exist!"
  mkdir -p "$SYMLINK_DIR"
  log "✅ Created symlink directory"
fi

# List all potential symlinks (handle case where glob doesn't match anything)
symlink_files=()
while IFS= read -r -d '' file; do
  symlink_files+=("$file")
done < <(find "$SYMLINK_DIR" -maxdepth 1 -name "*.yml" -print0 2>/dev/null || echo "")

# Print count of symlinks found
log "🔍 Found $(echo "${#symlink_files[@]}") potential .yml files"

if [[ ${#symlink_files[@]} -eq 0 ]]; then
  log "⚠️  No .yml files found in symlink directory '$SYMLINK_DIR'"
fi

# Check each potential symlink file
for SYMLINK in "${symlink_files[@]}"; do
  # Check if file exists (needed for safety)
  if [[ ! -e "$SYMLINK" ]]; then
    continue
  fi
  
  log "🔍 Checking: $SYMLINK"
  
  # Skip if not a symlink
  if [[ ! -L "$SYMLINK" ]]; then
    log "ℹ️  Found non-symlink file: $SYMLINK (skipping)"
    continue
  fi
  
  ((symlink_count++))
  
  # Get target path (not using readlink -f to avoid resolving broken links)
  REAL_FILE=$(readlink "$SYMLINK")
  # Resolve relative paths
  if [[ ! "$REAL_FILE" = /* ]]; then
    REAL_FILE="$(dirname "$SYMLINK")/$REAL_FILE"
  fi
  
  log "   → Points to: $REAL_FILE"
  
  # Check if target file exists
  if [[ ! -f "$REAL_FILE" ]]; then
    log "🗑️  Removing broken symlink: $SYMLINK → $REAL_FILE (file doesn't exist)"
    rm -f "$SYMLINK"
    ((broken_count++))
    continue
  fi
  
  # Get real path for exclusion checking
  REAL_PATH=$(readlink -f "$REAL_FILE" 2>/dev/null || echo "$REAL_FILE")
  
  # Check if symlink points to excluded file
  excluded=false
  for excluded_file in "${REAL_EXCLUDED_FILES[@]}"; do
    if [[ "$REAL_PATH" == "$excluded_file" ]]; then
      excluded=true
      break
    fi
  done
  
  if [[ "$excluded" == "true" ]]; then
    log "🗑️  Removing symlink to excluded file: $SYMLINK → $REAL_PATH"
    rm -f "$SYMLINK"
    ((excluded_count++))
    continue
  fi
  
  log "✅ Valid symlink: $SYMLINK → $REAL_PATH"
done

log "📊 Symlink summary: $symlink_count found, $broken_count broken, $excluded_count excluded"

# Rescan directory to get accurate count of remaining symlinks
remaining_symlinks=$(find "$SYMLINK_DIR" -type l -name "*.yml" 2>/dev/null | wc -l)
if [[ "$remaining_symlinks" -eq 0 ]]; then
  log "⚠️  No valid symlinks remain after cleanup, nothing to process"
  log "\n[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Update script complete (no work done)."
  exit 0
fi

log "\n🔄 Processing $remaining_symlinks Docker Compose files..."

# Reuse symlink_files array but update it after cleanup
symlink_files=()
while IFS= read -r -d '' file; do
  symlink_files+=("$file")
done < <(find "$SYMLINK_DIR" -maxdepth 1 -type l -name "*.yml" -print0 2>/dev/null || echo "")

# Main processing loop
processed_count=0
for COMPOSE_FILE in "${symlink_files[@]}"; do
  # Skip if not a file or not a symlink (additional safety check)
  if [[ ! -f "$COMPOSE_FILE" || ! -L "$COMPOSE_FILE" ]]; then
    log "⏭️  Skipping non-file or non-symlink: $COMPOSE_FILE"
    continue
  fi
  
  ((processed_count++))
  
  # Get real file path
  REAL_FILE=$(readlink -f "$COMPOSE_FILE" 2>/dev/null)
  
  # Double-check the file exists
  if [[ ! -f "$REAL_FILE" ]]; then
    log "⚠️  Broken symlink detected: $COMPOSE_FILE → $REAL_FILE"
    log "🗑️  Removing broken symlink"
    rm -f "$COMPOSE_FILE"
    continue
  fi
  
  # Skip if in excluded list
  excluded=false
  for excluded_file in "${REAL_EXCLUDED_FILES[@]}"; do
    if [[ "$REAL_FILE" == "$excluded_file" ]]; then
      excluded=true
      break
    fi
  done
  
  if [[ "$excluded" == "true" ]]; then
    log "⏭️  Skipping excluded file: $REAL_FILE"
    continue
  fi
  
  REAL_DIR=$(dirname "$REAL_FILE")
  ENV_FILE="$REAL_DIR/.env"
  
  log "\n📂 Processing: $COMPOSE_FILE (→ $REAL_FILE)"
  
  # Load .env if present
  if [ -f "$ENV_FILE" ]; then
    log "📦 Loading env from $ENV_FILE"
    set -o allexport
    # shellcheck disable=SC1090
    source "$ENV_FILE" || log "⚠️  Warning: Error sourcing .env file"
    set +o allexport
  else
    log "ℹ️  No .env found in $REAL_DIR, continuing without"
  fi
  
  # Check if docker compose is available
  if ! command -v docker &> /dev/null; then
    log "❌ Docker is not available. Please ensure Docker is installed and in your PATH."
    exit 1
  fi
  
  # Extract image names and store current digests
  log "🔍 Extracting images from compose file..."
  
  # Use a temporary file to capture potential errors
  TMP_CONFIG_OUTPUT=$(mktemp)
  # Note: Use docker-compose directly if compose subcommand fails
  if docker compose -f "$REAL_FILE" config > "$TMP_CONFIG_OUTPUT" 2>&1 || \
     docker-compose -f "$REAL_FILE" config > "$TMP_CONFIG_OUTPUT" 2>&1; then
    IMAGES=$(awk '/image:/ {print $2}' "$TMP_CONFIG_OUTPUT")
    rm -f "$TMP_CONFIG_OUTPUT"
  else
    log "⚠️  Error when parsing docker-compose file:"
    cat "$TMP_CONFIG_OUTPUT" >> "$LOG_FILE"
    if [[ "$VERBOSE" == "true" ]]; then
      cat "$TMP_CONFIG_OUTPUT"
    fi
    rm -f "$TMP_CONFIG_OUTPUT"
    log "⏭️  Skipping file due to parsing errors"
    continue
  fi
  
  if [[ -z "$IMAGES" ]]; then
    log "⚠️  No images found in compose file: $REAL_FILE"
    continue
  fi
  
  log "📋 Found images:"
  for img in $IMAGES; do
    log "  - $img"
    
    # Check if image exists locally
    if ! docker image inspect "$img" &> /dev/null; then
      log "    ⚠️  Image not found locally"
      # Store "none" as old digest
      OLD_DIGEST="none"
    else
      # Store old digest for comparison after pull
      OLD_DIGEST=$(docker image inspect --format='{{index .RepoDigests 0}}' "$img" 2>/dev/null || echo "none")
      digest_preview=${OLD_DIGEST:0:60}
      log "    📌 Current digest: ${digest_preview}..."
    fi
    
    # Create a safe filename for the digest
    DIGEST_FILE="$TMP_DIR/$(basename "$REAL_FILE")-$(echo "$img" | tr '/:@' '_')-old.digest"
    echo "$OLD_DIGEST" > "$DIGEST_FILE"
  done
  
  # Pull images, working in the actual directory to respect .env variables
  log "⬇️  Pulling images..."
  (
    cd "$REAL_DIR" || { 
      log "❌ Failed to change to directory: $REAL_DIR"; 
      exit 1; # Exit the subshell, not the whole script
    }
    
    # Try docker compose first, fall back to docker-compose
    pull_cmd="docker compose -f \"$REAL_FILE\" pull"
    if ! docker compose version &>/dev/null; then
      pull_cmd="docker-compose -f \"$REAL_FILE\" pull"
    fi
    
    # Execute the pull command with output visible when verbose
    if eval "$pull_cmd" 2>&1 | tee -a "$LOG_FILE"; then
      log "✅ Pull completed for: $REAL_FILE"
    else
      log "❌ Pull failed for: $REAL_FILE"
      FAILED_PULLS+=("$REAL_FILE")
      exit 1  # Exit the subshell with error
    fi
  )
  pull_exit_code=$?
  
  # Track if any container was updated in this compose file
  local_updated=false
  
  # If pull failed completely, continue to next compose file
  if [[ $pull_exit_code -ne 0 ]]; then
    log "⏭️ Skipping further processing due to pull failure"
    continue
  fi
  
  # Compare digests to identify actual changes
  log "🔍 Comparing digests..."
  for img in $IMAGES; do
    # Get image name without tag for better identification
    img_name=$(echo "$img" | awk -F ':' '{print $1}' | awk -F '/' '{print $NF}')
    img_version=$(echo "$img" | awk -F ':' '{if (NF>1) print $2; else print "latest"}')
    
    # Create a safe filename for the digest
    DIGEST_FILE="$TMP_DIR/$(basename "$REAL_FILE")-$(echo "$img" | tr '/:@' '_')-old.digest"
    
    # Ensure digest file exists
    if [[ ! -f "$DIGEST_FILE" ]]; then
      log "⚠️  Missing digest file for $img, skipping comparison"
      continue
    fi
    
    OLD_DIGEST=$(cat "$DIGEST_FILE")
    
    # Check if the image exists now
    if ! docker image inspect "$img" &> /dev/null; then
      log "⚠️  Image $img still not found after pull attempt"
      continue
    fi
    
    NEW_DIGEST=$(docker image inspect --format='{{index .RepoDigests 0}}' "$img" 2>/dev/null || echo "none")
    
    if [[ "$OLD_DIGEST" != "$NEW_DIGEST" && "$OLD_DIGEST" != "none" && "$NEW_DIGEST" != "none" ]]; then
      log "🔄 Updated: $img"
      old_preview=${OLD_DIGEST:0:60}
      new_preview=${NEW_DIGEST:0:60}
      log "   🕒 Old: ${old_preview}..."
      log "   ✅ New: ${new_preview}..."
      
      # Add to tracked updates
      UPDATED_CONTAINERS+=("$img_name:$img_version")
      local_updated=true
    else
      log "✔️  No change: $img"
      # If verbose, show more details
      if [[ "$VERBOSE" == "true" ]]; then
        old_preview=${OLD_DIGEST:0:60}
        new_preview=${NEW_DIGEST:0:60}
        log "   🕒 Old: ${old_preview}..."
        log "   ✅ Current: ${new_preview}..."
      fi
    fi
  done
  
  # Restart containers if updates were found and not in test mode
  if $local_updated; then
    if [[ "$TEST_MODE" != "true" ]]; then
      log "🚀 Restarting containers..."
      (
        cd "$REAL_DIR" || { 
          log "❌ Failed to change to directory: $REAL_DIR"; 
          exit 1; # Exit the subshell, not the whole script
        }
        
        # Try docker compose first, fall back to docker-compose
        restart_cmd="docker compose -f \"$REAL_FILE\" up -d"
        if ! docker compose version &>/dev/null; then
          restart_cmd="docker-compose -f \"$REAL_FILE\" up -d"
        fi
        
        # Execute the restart command with output visible when verbose
        if eval "$restart_cmd" 2>&1 | tee -a "$LOG_FILE"; then
          log "✅ Containers restarted successfully"
        else
          log "❌ Failed to restart containers"
          exit 1  # Exit the subshell with error
        fi
      )
      restart_exit_code=$?
      
      if [[ $restart_exit_code -ne 0 ]]; then
        log "⚠️ Container restart had issues - check the logs for details"
      fi
    else
      log "🧪 Test mode: skipping container restart"
    fi
  else
    ((NO_UPDATES++))
    log "✅ No updates required"
  fi
  
  log "----------------------------------"
done

if [[ "$processed_count" -eq 0 ]]; then
  log "⚠️  No compose files were processed!"
fi

# Clean up unused images
log "\n🧹 Cleaning up unused images..."
docker image prune -f 2>&1 | tee -a "$LOG_FILE"

# Format and send Discord message
if [[ ${#UPDATED_CONTAINERS[@]} -gt 0 ]]; then
  EMBED_CONTENT=""
  
  # Sort containers for better readability
  IFS=$'\n' SORTED_CONTAINERS=($(sort <<<"${UPDATED_CONTAINERS[*]}"))
  unset IFS
  
  for container in "${SORTED_CONTAINERS[@]}"; do
    container_name=$(echo "$container" | awk -F ':' '{print $1}')
    version=$(echo "$container" | awk -F ':' '{print $2}')
    emoji=${SERVICE_EMOJIS[$container_name]:-":whale:"}
    
    EMBED_CONTENT+=$(cat <<EOF
{
  "name": "$emoji $container_name",
  "value": "${version:-latest}",
  "inline": true
},
EOF
)
  done
  
  # Generate error fields if any pulls failed
  ERROR_CONTENT=""
  if [[ ${#FAILED_PULLS[@]} -gt 0 ]]; then
    for failed in "${FAILED_PULLS[@]}"; do
      ERROR_CONTENT+=$(cat <<EOF
{
  "name": "❌ Failed Pull",
  "value": "$(basename "$failed")",
  "inline": true
},
EOF
)
    done
    ERROR_CONTENT=${ERROR_CONTENT%,}  # Strip last comma
  fi
  
  # Combine fields
  FIELDS_CONTENT=${EMBED_CONTENT%,}  # Strip last comma
  if [[ -n "$ERROR_CONTENT" ]]; then
    FIELDS_CONTENT+=",${ERROR_CONTENT}"
  fi
  
  # Determine color based on errors
  COLOR=$COLOUR_UPDATE
  if [[ ${#FAILED_PULLS[@]} -gt 0 ]]; then
    COLOR=$COLOUR_ERROR
  fi
  
  # Build the payload
  PAYLOAD=$(cat <<EOF
{
  "embeds": [
    {
      "title": "⬆️ Docker Image Updates",
      "description": "Updates were found for ${#UPDATED_CONTAINERS[@]} containers.$([[ ${#FAILED_PULLS[@]} -gt 0 ]] && echo "\n⚠️ Some pulls failed! Check logs." || echo "")",
      "color": $COLOR,
      "timestamp": "$TIMESTAMP",
      "fields": [$FIELDS_CONTENT]
    }
  ]
}
EOF
)
elif [[ ${#FAILED_PULLS[@]} -gt 0 ]]; then
  # Only errors occurred
  ERROR_CONTENT=""
  for failed in "${FAILED_PULLS[@]}"; do
    ERROR_CONTENT+=$(cat <<EOF
{
  "name": "❌ Failed Pull",
  "value": "$(basename "$failed")",
  "inline": true
},
EOF
)
  done
  ERROR_CONTENT=${ERROR_CONTENT%,}  # Strip last comma
  
  PAYLOAD=$(cat <<EOF
{
  "embeds": [
    {
      "title": "⚠️ Docker Update Check Failed",
      "description": "Some pulls failed! Check logs.",
      "color": $COLOUR_ERROR,
      "timestamp": "$TIMESTAMP",
      "fields": [$ERROR_CONTENT]
    }
  ]
}
EOF
)
else
  # No updates, no errors
  PAYLOAD=$(cat <<EOF
{
  "embeds": [
    {
      "title": "✅ No Docker Updates Available",
      "description": "All $NO_UPDATES checked compose files are up to date.",
      "color": $COLOUR_NO_UPDATE,
      "timestamp": "$TIMESTAMP"
    }
  ]
}
EOF
)
fi

# Send Discord notification
log "\n📧 Sending Discord notification..."
if curl -s -X POST -H "Content-Type: application/json" \
  -d "$PAYLOAD" \
  "$DISCORD_WEBHOOK_URL" > /dev/null; then
  log "✅ Discord notification sent successfully"
else
  log "❌ Failed to send Discord notification"
fi

# Summarize results
log "\n📊 Results Summary:"
log "  • Compose files processed: $processed_count"
log "  • Containers updated: ${#UPDATED_CONTAINERS[@]}"
log "  • Failed pulls: ${#FAILED_PULLS[@]}"
log "  • Containers with no updates: $NO_UPDATES"

if [[ ${#UPDATED_CONTAINERS[@]} -gt 0 ]]; then
  log "\n🔄 Updated containers:"
  for container in "${UPDATED_CONTAINERS[@]}"; do
    log "  • $container"
  done
fi

if [[ ${#FAILED_PULLS[@]} -gt 0 ]]; then
  log "\n⚠️ Failed pulls:"
  for failed in "${FAILED_PULLS[@]}"; do
    log "  • $(basename "$failed")"
  done
fi

log "\n[$(date '+%Y-%m-%d %H:%M:%S')] ✅ Update script complete."
