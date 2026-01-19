# Contributing to Trace

Thank you for your interest in contributing to Trace! This document provides guidelines and information for contributors.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Code Style](#code-style)
- [Testing](#testing)
- [Pull Request Process](#pull-request-process)
- [Reporting Issues](#reporting-issues)

## Code of Conduct

By participating in this project, you agree to maintain a respectful and inclusive environment. Please:

- Be respectful and constructive in discussions
- Welcome newcomers and help them get started
- Focus on what is best for the community and the project
- Accept constructive criticism gracefully

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/Trace.git
   cd Trace
   ```
3. **Add the upstream remote**:
   ```bash
   git remote add upstream https://github.com/junkim100/Trace.git
   ```

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://github.com/astral-sh/uv) package manager
- macOS 12.0+ (for full functionality)

### Installation

```bash
# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install Python dependencies
uv sync

# Install Node.js dependencies for Electron
cd electron && npm install && cd ..
```

### Environment Setup

1. Copy the environment template (if available) or create `.env`:
   ```bash
   echo "OPENAI_API_KEY=your-api-key-here" > .env
   ```

2. Grant required macOS permissions when running the app:
   - Screen Recording
   - Accessibility
   - Location Services (optional)

### Running in Development

```bash
# Start the Electron app (includes Python backend)
cd electron && npm start

# Or run Python backend separately
uv run python -m src.core.services start

# Run a specific module
uv run python -m src.capture.daemon
uv run python -m src.chat.api chat "What did I do today?"
```

## Making Changes

### Branch Naming

Use descriptive branch names:
- `feature/add-spotify-support` - New features
- `fix/screenshot-dedup-bug` - Bug fixes
- `docs/update-api-reference` - Documentation
- `refactor/simplify-capture-daemon` - Code refactoring

### Commit Messages

Follow conventional commit format:

```
type: short description

Longer description if needed.

Co-Authored-By: Your Name <your@email.com>
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
```
feat: add Apple Music now playing detection

fix: handle missing window title in foreground capture

docs: add API cost estimates to README
```

## Code Style

### Python

We use [Ruff](https://github.com/astral-sh/ruff) for linting and formatting.

```bash
# Check for issues
uv run ruff check src/

# Auto-fix issues
uv run ruff check --fix src/

# Format code
uv run ruff format src/
```

**Guidelines:**
- Use type hints for function parameters and return values
- Use dataclasses or Pydantic models for structured data
- Keep functions focused and under 50 lines when possible
- Use descriptive variable names
- Add docstrings to public functions and classes

### TypeScript/React (Electron)

```bash
cd electron

# Lint
npm run lint

# Format
npm run format
```

### File Organization

```
src/
├── capture/        # Activity capture modules
├── evidence/       # Text extraction (OCR, PDF)
├── summarize/      # Hourly summarization
├── revise/         # Daily revision
├── jobs/           # Job scheduling
├── chat/           # Chat interface
│   └── agentic/    # Multi-step query planning
├── retrieval/      # Search strategies
├── graph/          # Graph operations
├── db/             # Database operations
├── core/           # Service management, utilities
└── platform/       # macOS-specific integrations
```

## Testing

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run specific test file
uv run pytest tests/test_capture.py

# Run with coverage
uv run pytest tests/ --cov=src --cov-report=html

# Run e2e tests (requires permissions)
uv run pytest tests/e2e/
```

### Writing Tests

- Place tests in `tests/` mirroring the `src/` structure
- Use descriptive test names: `test_screenshot_deduplication_skips_identical_frames`
- Mock external APIs (OpenAI) in unit tests
- Use fixtures for common setup

Example:
```python
import pytest
from src.capture.dedup import compute_phash, is_duplicate

def test_identical_images_are_duplicates(tmp_path):
    """Two identical images should be detected as duplicates."""
    image_path = tmp_path / "test.png"
    # Create test image...

    hash1 = compute_phash(image_path)
    hash2 = compute_phash(image_path)

    assert is_duplicate(hash1, hash2, threshold=5)
```

## Pull Request Process

1. **Update your fork**:
   ```bash
   git fetch upstream
   git rebase upstream/main
   ```

2. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

3. **Make your changes** and commit them

4. **Run checks locally**:
   ```bash
   uv run ruff check --fix src/
   uv run ruff format src/
   uv run pytest tests/
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Open a Pull Request** on GitHub with:
   - Clear title describing the change
   - Description of what and why
   - Link to related issue (if applicable)
   - Screenshots for UI changes

### PR Review Checklist

- [ ] Code follows project style guidelines
- [ ] Tests added/updated for new functionality
- [ ] Documentation updated if needed
- [ ] No sensitive data (API keys, personal info) included
- [ ] Commits are clean and well-described

## Reporting Issues

### Bug Reports

Include:
- **Description**: What happened vs. what you expected
- **Steps to reproduce**: Minimal steps to trigger the bug
- **Environment**: macOS version, Python version, app version
- **Logs**: Relevant logs from `~/Library/Application Support/Trace/logs/`
- **Screenshots**: If applicable

### Feature Requests

Include:
- **Problem**: What problem does this solve?
- **Proposal**: How should it work?
- **Alternatives**: Other solutions you considered
- **Context**: Why is this important to you?

## Project Architecture

Before contributing, familiarize yourself with:

- **[Architecture Overview](docs/architecture.md)** - System design
- **[LLM Pipeline](docs/llm-pipeline.md)** - AI models and prompts
- **[Database Schema](docs/database.md)** - Data structures
- **[API Reference](docs/api.md)** - Available APIs

## Questions?

- Open a [GitHub Discussion](https://github.com/junkim100/Trace/discussions) for questions
- Check existing [Issues](https://github.com/junkim100/Trace/issues) for known problems
- Read the [Documentation](docs/) for technical details

---

Thank you for contributing to Trace!
