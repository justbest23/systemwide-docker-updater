#!/bin/bash

# Directory for symlinks
SYMLINK_DIR="/opt/image-updater/docker-compose-finder/compose-links"

# Exclude list - Docker Compose files you don't want to add to symlink folder
EXCLUDED_FILES=(
  "/example/excluded/file.yml"
)

# Create the symlink directory if it doesn't exist
mkdir -p "$SYMLINK_DIR"

# Find all docker-compose-related files
# List where you want to look for compose files (Space separated)
directories="/opt /etc /home/your_username_here"
DOCKER_COMPOSE_FILES=$(find $directories -type f \( -iname "*docker-compose*.yml" -o -iname "*docker-compose*.yaml" \) 2>/dev/null)

# Clear out duplicate name tracking
declare -A USED_NAMES

# Process each file found
for COMPOSE_FILE in $DOCKER_COMPOSE_FILES; do
    # If in exclusion list, remove corresponding symlink if it exists
    if [[ " ${EXCLUDED_FILES[@]} " =~ " ${COMPOSE_FILE} " ]]; then
        BASENAME=$(basename "$COMPOSE_FILE")
        HASH=$(echo -n "$COMPOSE_FILE" | sha1sum | cut -c1-8)
        ALT_NAME="${BASENAME%.yml}-${HASH}.yml"

        # Try both naming variants
        for SYMLINK_NAME in "$BASENAME" "$ALT_NAME"; do
            SYMLINK_PATH="$SYMLINK_DIR/$SYMLINK_NAME"
            if [[ -L "$SYMLINK_PATH" ]]; then
                echo "Removing symlink for excluded file: $SYMLINK_PATH"
                rm "$SYMLINK_PATH"
            fi
        done
        continue
    fi

    # Build symlink name
    BASENAME=$(basename "$COMPOSE_FILE")
    if [[ -n "${USED_NAMES[$BASENAME]}" ]]; then
        HASH=$(echo -n "$COMPOSE_FILE" | sha1sum | cut -c1-8)
        SYMLINK_NAME="${BASENAME%.yml}-${HASH}.yml"
    else
        SYMLINK_NAME="$BASENAME"
        USED_NAMES[$BASENAME]=1
    fi

    SYMLINK_PATH="$SYMLINK_DIR/$SYMLINK_NAME"

    # Create or refresh symlink
    if [[ -L "$SYMLINK_PATH" && "$(readlink -f "$SYMLINK_PATH")" == "$COMPOSE_FILE" ]]; then
        echo "Symlink already correct: $SYMLINK_PATH"
    else
        echo "Creating symlink for $COMPOSE_FILE"
        ln -sf "$COMPOSE_FILE" "$SYMLINK_PATH"
    fi
done

# Remove symlinks pointing to deleted files
for EXISTING_SYMLINK in "$SYMLINK_DIR"/*; do
    if [[ -L "$EXISTING_SYMLINK" ]]; then
        TARGET_PATH=$(readlink -f "$EXISTING_SYMLINK")
        if [[ ! -f "$TARGET_PATH" ]]; then
            echo "Removing dead symlink: $EXISTING_SYMLINK"
            rm "$EXISTING_SYMLINK"
        fi
    fi
done

echo "Symlink folder has been updated."
