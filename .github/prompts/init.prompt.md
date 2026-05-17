---
description: "Initialize the project: set up the Python environment, install dependencies, and download required Java/MPXJ assets."
agent: "agent"
argument-hint: "Optional: specific setup step to focus on"
---

# Project Initialization

Follow the steps below to set up the **Project Offline** development environment from scratch.

## Steps

### 1. Verify prerequisites
- Confirm Python 3.12 is available: `python --version`
- Confirm `pip` is available: `pip --version`

### 2. Install Python dependencies
Run from the workspace root:
```
pip install -r requirements.txt
```
The required packages are: `PyQt5`, `mpxj`, `jpype1`.

### 3. Download MPXJ Java library
Run the download helper:
```
python tools/download_mpxj.py
```

### 4. Download OpenJDK (Java runtime)
Run the download helper:
```
python tools/download_openjdk.py
```

### 5. Verify the setup
Launch the application to confirm everything works:
```
python src/main.py
```

## Project Structure Overview
- `src/` — application source code (UI, logic, views)
- `src/views/` — individual view modules (Gantt, tasks, resources, etc.)
- `tools/` — setup/download helpers
- `requirements.txt` — Python package dependencies
