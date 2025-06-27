# Architecture

This document describes the architecture and design principles of the Reddit Persona Validator system.

## Overview

The Reddit Persona Validator is built with a modular, layered architecture that separates concerns and allows for flexibility in deployment and usage patterns.

## Component Diagram

```
┌─────────────────────────┐
│       Interfaces        │
│  ┌─────┬──────┬──────┐  │
│  │ CLI │ GUI  │ API  │  │
│  └─────┴──────┴──────┘  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│         Core            │
│  ┌─────────────────────┐ │
│  │      Validator      │ │
│  └──────────┬──────────┘ │
│  ┌──────────▼──────────┐ │
│  │   Browser Engine    │ │
│  └──────────┬──────────┘ │
│  ┌──────────▼──────────┐ │
│  │   Email Verifier    │ │
│  └─────────────────────┘ │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│        Analysis         │
│  ┌─────────┬──────────┐  │
│  │ DeepSeek │ Claude  │  │
│  └─────────┴──────────┘  │
│  ┌─────────────────────┐  │
│  │       Scorer        │  │
│  └─────────────────────┘  │
└───────────┬─────────────┘
            │
┌───────────▼─────────────┐
│         Utils           │
│  ┌─────────────────────┐  │
│  │    Proxy Rotator    │  │
│  └─────────────────────┘  │
│  ┌─────────────────────┐  │
│  │   Cookie Manager    │  │
│  └─────────────────────┘  │
│  ┌─────────────────────┐  │
│  │   Config Loader     │  │
│  └─────────────────────┘  │
└─────────────────────────┘
```

## Layers

### 1. Interfaces

Provides different ways to interact with the system:

- **CLI**: Command-line interface with progress bars and logging
- **GUI**: PySimpleGUI-based graphical interface with dark/light themes
- **API**: FastAPI-based REST API with Swagger documentation

### 2. Core

Contains the main business logic:

- **Validator**: Orchestrates the validation process
- **Browser Engine**: Manages UC (Undetectable Chrome) for web automation
- **Email Verifier**: Handles IMAP connections for email verification

### 3. Analysis

Handles AI-powered persona analysis:

- **DeepSeek Adapter**: Connects to DeepSeek API for primary analysis
- **Claude Adapter**: Alternative AI provider
- **Scorer**: Implements trust algorithms based on various factors

### 4. Utils

Provides supporting functionality:

- **Proxy Rotator**: Manages proxy rotation with health checks
- **Cookie Manager**: Encrypts and stores session cookies
- **Config Loader**: Loads configuration from YAML and environment variables

## Data Flow

1. User initiates validation through one of the interfaces
2. Validator orchestrates the process:
   - Browser Engine handles Reddit interaction
   - Email Verifier confirms linked email
3. Analysis components evaluate the persona:
   - AI adapters analyze content patterns
   - Scorer combines factors into a trust score
4. Results are returned to the user through the original interface

## Design Principles

- **Modularity**: Components are loosely coupled for easier maintenance
- **Abstraction**: Implementation details are hidden behind clear interfaces
- **Security**: Sensitive data is encrypted, proxies are rotated
- **Testability**: Components are designed for comprehensive testing
- **Configurability**: Behavior can be adjusted through configuration

## Technology Stack

- **Language**: Python 3.10+
- **Web Automation**: UC (Undetectable Chrome)
- **Email**: IMAP for Hotmail verification
- **AI**: DeepSeek and Claude APIs
- **Security**: Fernet encryption
- **Interfaces**: CLI (rich), GUI (PySimpleGUI), API (FastAPI)
- **Deployment**: Docker, AWS Lightsail

## Future Considerations

- Expand to additional email providers
- Support for more social media platforms
- Enhanced AI analysis with custom models
- Distributed architecture for high-volume processing
