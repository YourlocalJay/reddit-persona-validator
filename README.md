# Reddit Persona Validator

![Version](https://img.shields.io/badge/version-0.1.0-blue)
![Python](https://img.shields.io/badge/Python-3.10+-green)
![License](https://img.shields.io/badge/license-MIT-orange)

A comprehensive system for validating Reddit personas with Hotmail email verification and AI-powered analysis.

![GUI Demo](docs/IMAGES/gui_demo.gif)

## Features

- **Multi-mode Validation**: Choose between CLI, GUI, or API interfaces
- **AI-powered Persona Analysis**: Leverages DeepSeek and Claude APIs for content evaluation
- **Email Verification**: Confirms Reddit accounts with linked Hotmail addresses
- **Encrypted Session Storage**: Securely manages cookies and authentication data
- **Proxy Management**: Built-in rotation with health checks
- **Trust Scoring**: Algorithm combining multiple validation factors

## Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/YourlocalJay/reddit-persona-validator.git
cd reddit-persona-validator

# Start all services
docker compose up -d

# Access the API documentation
# Open in browser: http://localhost:8000/docs
```

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/YourlocalJay/reddit-persona-validator.git
cd reddit-persona-validator

# Create and activate virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp config/.env.example config/.env
# Edit config/.env with your API keys and settings

# Start the application (choose one)
python src/interfaces/cli.py  # Command-line interface
python src/interfaces/gui.py  # Graphical user interface
python src/interfaces/api.py  # API server
```

## Configuration

Edit `config/config.yaml` to customize:

- Connection timeouts
- Proxy settings
- AI analysis parameters
- Scoring thresholds
- Interface preferences

## Documentation

- [Setup Guide](docs/SETUP.md) - Detailed installation instructions
- [Architecture](docs/ARCHITECTURE.md) - System design and components
- [API Reference](docs/API.md) - Endpoint documentation
- [Troubleshooting](docs/TROUBLESHOOTING.md) - Common issues and solutions

## Development

```bash
# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
pytest

# Check code style
black .
flake8 .

# Generate documentation
mkdocs build
```

## License

MIT License - See [LICENSE](LICENSE) file for details.

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Commit changes: `git commit -am 'Add new feature'`
4. Push to branch: `git push origin feature/my-feature`
5. Submit a pull request
