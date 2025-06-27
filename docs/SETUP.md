# Setup Guide

This document provides detailed setup instructions for the Reddit Persona Validator on different operating systems.

## Prerequisites

- Python 3.10 or higher
- Git
- Docker (optional, but recommended)

## Installation

### Windows

1. **Install Python 3.10+**
   - Download and install from [python.org](https://www.python.org/downloads/)
   - Ensure you check "Add Python to PATH" during installation

2. **Install Git**
   - Download and install from [git-scm.com](https://git-scm.com/download/win)

3. **Clone the Repository**
   ```powershell
   git clone https://github.com/YourlocalJay/reddit-persona-validator.git
   cd reddit-persona-validator
   ```

4. **Set Up Virtual Environment**
   ```powershell
   python -m venv venv
   .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

5. **Configure Environment**
   ```powershell
   copy config\.env.example config\.env
   # Edit config\.env with your API keys and settings
   ```

### macOS

1. **Install Python 3.10+**
   ```bash
   brew install python@3.10
   ```

2. **Install Git**
   ```bash
   brew install git
   ```

3. **Clone the Repository**
   ```bash
   git clone https://github.com/YourlocalJay/reddit-persona-validator.git
   cd reddit-persona-validator
   ```

4. **Set Up Virtual Environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Configure Environment**
   ```bash
   cp config/.env.example config/.env
   # Edit config/.env with your API keys and settings
   ```

### Linux

1. **Install Python 3.10+**
   ```bash
   sudo apt update
   sudo apt install python3.10 python3.10-venv python3-pip
   ```

2. **Install Git**
   ```bash
   sudo apt install git
   ```

3. **Clone the Repository**
   ```bash
   git clone https://github.com/YourlocalJay/reddit-persona-validator.git
   cd reddit-persona-validator
   ```

4. **Set Up Virtual Environment**
   ```bash
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

5. **Configure Environment**
   ```bash
   cp config/.env.example config/.env
   # Edit config/.env with your API keys and settings
   ```

## Docker Setup (All Platforms)

1. **Install Docker**
   - Windows/Mac: Install [Docker Desktop](https://www.docker.com/products/docker-desktop)
   - Linux: Follow [Docker Engine installation](https://docs.docker.com/engine/install/)

2. **Clone the Repository**
   ```bash
   git clone https://github.com/YourlocalJay/reddit-persona-validator.git
   cd reddit-persona-validator
   ```

3. **Configure Environment**
   ```bash
   cp config/.env.example config/.env
   # Edit config/.env with your API keys and settings
   ```

4. **Build and Run with Docker**
   ```bash
   docker compose -f infrastructure/compose.yml up -d
   ```

## Verification

To verify your installation:

1. **CLI Interface**
   ```bash
   python src/interfaces/cli.py --help
   ```

2. **GUI Interface**
   ```bash
   python src/interfaces/gui.py
   ```

3. **API Interface**
   ```bash
   python src/interfaces/api.py
   # Then open http://localhost:8000/docs in your browser
   ```

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common issues and solutions.
