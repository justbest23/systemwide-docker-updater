# Docker Compose Finder & Symlinker

This project provides a Bash utility to locate all Docker Compose files on a system and create symlinks to them in a single, central directory for easier management and discovery. It also supports exclusion rules and automatic cleanup of stale links.

---

## 📂 Features

- Recursively scans common directories (`/opt`, `/etc`, `/home/troggoman`) for files matching:
  - `*docker-compose*.yml`
  - `*docker-compose*.yaml`
- Automatically generates symlinks to found files in a configurable target directory.
- Avoids name collisions by appending a short hash to duplicate filenames.
- Supports an exclusion list to omit certain Compose files from being linked.
- Removes symlinks that point to files that no longer exist.

---

## 📁 Directory Structure

```
/opt/image-updater/
├── compose-update.log           # Full logs
├── docker-compose-finder        # Compose finder dir
│   ├── compose_finder.sh        # Compose finder Script
│   └── compose-links            # Symlink dir
|       ├── docker-compose-3da24ece.yml -> /opt/mediaserver/conf/docker-compose.yml
└── image-updater.sh            # Main script
```

---

## 🧑‍💻 Usage

### 1. Clone the Repository

```bash
git clone https://github.com/your-username/docker-compose-finder.git
cd docker-compose-finder
```

### 2. Run the Script

```bash
chmod +x docker-compose-finder.sh
./docker-compose-finder.sh
```

This will:

- Create `/opt/image-updater/docker-compose-finder/compose-links` if it doesn't exist.
- Populate it with symlinks to detected Docker Compose files.
- Remove links to any excluded or deleted files.

---

## ⚙️ Configuration

### Directory where symlinks are stored

Edit this variable in the script if you want to change the output folder:

```bash
SYMLINK_DIR="/opt/image-updater/docker-compose-finder/compose-links"
```

### Directories to search

In `find-compose-files.sh` or directly in the script:

```bash
directories="/opt /etc /home/troggoman"
```

### Excluded files (won’t be symlinked)

```bash
EXCLUDED_FILES=(
  "/opt/mediaserver/conf/backup-docker-compose.yml"
  "/opt/mediaserver/docker-compose.override.yml"
)
```

---

## 🧹 Housekeeping

The script ensures:

- No duplicate symlink names by appending an 8-character SHA1 hash when needed.
- Stale or broken symlinks (pointing to deleted files) are automatically removed.
- If a file is listed in the exclusions list and a symlink exists, the symlink will be removed.

---

## 🐧 Requirements

- Linux or WSL
- Bash
- Standard UNIX utilities: `find`, `sha1sum`, `readlink`, `ln`

---

## 📝 Example Output

```bash
Creating symlink for /opt/myapp/docker-compose.yml
Creating symlink for /etc/containers/docker-compose.production.yaml
Removing symlink for excluded file: /opt/image-updater/docker-compose-finder/compose-links/backup-docker-compose.yml
Removing dead symlink: /opt/image-updater/docker-compose-finder/compose-links/old-compose.yml
Symlink folder has been updated.
```

---

## 📬 Contributions

Pull requests and issues are welcome. If you'd like to extend functionality, improve compatibility, or suggest features, feel free to contribute.

---

## 📜 License

MIT License
