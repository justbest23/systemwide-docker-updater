# README is a WIP!

## This README does not talk about the image-updater.sh script. THIS IS A BAD README

# Systemwide Docker Updater

**Systemwide Docker Updater** is a comprehensive tool that helps manage and update Docker Compose applications across an entire system. This repository provides both **Bash** and **Python** implementations to scan, centralize, and update Docker Compose configurations.

## Features

- 🔍 **Recursive Compose File Discovery**
- 🔗 **Centralized Symlink Management**
- ♻️ **Image Update Automation**
- ⚠️ **Name Collision Handling**
- 🚫 **Exclusion Support**
- 🧹 **Cleanup of Broken Symlinks**
- 🐍 **Python alternative implementation with logging and cleaner syntax**

---

## 🔧 Bash Scripts

### `compose-finder.sh`

- Recursively scans predefined directories (`/opt`, `/etc`, `/home/troggoman`) for Docker Compose files (`*docker-compose*.yml` and `*docker-compose*.yaml`).
- Creates symlinks to found files in a centralized target directory.
- Handles duplicate file names by appending a unique hash.
- Allows for directory exclusions.

**Usage**:
```bash
./compose-finder.sh [target_directory]
```

### `image-updater.sh`

- Loops through the symlinked Compose files and updates Docker images defined within them.

**Usage**:
```bash
./image-updater.sh
```

---

## 🐍 Python Scripts

### `compose_finder.py`

- A Python equivalent of `compose-finder.sh`.
- Scans the system for Docker Compose files and creates symlinks in a target directory.
- Offers cleaner and more modular code using Python's standard libraries.

### `image_updater.py`

- Parses Docker Compose YAML files to identify services and associated images.
- Uses the Docker CLI to check and update outdated images.
- Handles YAML parsing and error reporting more robustly than the Bash counterpart.

**Running the Python scripts**:
```bash
python3 compose_finder.py [target_directory]
python3 image_updater.py
```

---

## 🔁 Suggested Cronjob Setup

To automate this updater, consider adding a cronjob like the following:

```bash
0 * * * * /path/to/compose-finder.sh /opt/docker-links
30 * * * * /path/to/image-updater.sh
```

Or using the Python version:

```bash
0 * * * * /usr/bin/python3 /path/to/compose_finder.py /opt/docker-links
30 * * * * /usr/bin/python3 /path/to/image_updater.py
```

---

## 🧪 Testing

Ensure you have Docker installed and Compose files available for testing.

To test the Python scripts:

```bash
python3 compose_finder.py /tmp/test-docker-links
python3 image_updater.py
```

To test the Bash scripts:

```bash
./compose-finder.sh /tmp/test-docker-links
./image-updater.sh
```

---

## 📄 License

This project is licensed under the [GNU GPLv3 License](https://www.gnu.org/licenses/gpl-3.0.html).

## 🤝 Contributing

Contributions and improvements are welcome. Fork the repository, make your changes, and submit a pull request.

## 👨‍💻 Author

Created by [justbest23](https://github.com/justbest23)
