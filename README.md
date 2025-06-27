# Reddit Persona Validator

![GUI Demo](docs/IMAGES/gui_demo.gif)

## Features
- Multi-mode validation (CLI/GUI/API)
- AI-powered persona analysis
- Encrypted session storage

## Quick Start
```bash
docker compose up -d
http://localhost:8000/docs  # API
python src/interfaces/gui.py # GUI
```

## Overview
Reddit Persona Validator is a comprehensive tool designed to validate Reddit user personas through multiple verification methods, including email validation, account age analysis, karma evaluation, and AI-powered content assessment.

## Key Components
- **Reddit Integration**: Securely authenticate and analyze Reddit profiles
- **Email Verification**: Validate ownership through Hotmail/Outlook accounts
- **AI Analysis**: Leverage DeepSeek and Claude models for content authenticity assessment
- **Multiple Interfaces**: Choose between CLI, GUI, or API based on your needs

## Security Features
- Encrypted cookie storage
- Proxy rotation with health checks
- Comprehensive authentication system

## Installation
See [SETUP.md](docs/SETUP.md) for detailed installation instructions for all operating systems.

## Documentation
Full documentation is available in the [docs](docs/) directory.

## License
MIT
