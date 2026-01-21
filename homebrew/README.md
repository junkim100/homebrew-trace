# Homebrew Tap for Trace

This is a Homebrew tap for installing [Trace](https://github.com/junkim100/Trace).

## Installation

```bash
# Add the tap
brew tap junkim100/trace https://github.com/junkim100/Trace.git --custom-remote

# Install Trace
brew install --cask trace
```

Or install directly without adding the tap:

```bash
brew install --cask junkim100/trace/trace
```

## What This Does

The cask will:
1. Download the appropriate DMG for your Mac (Apple Silicon or Intel)
2. Install Trace.app to /Applications
3. **Automatically remove the quarantine flag** (no more "damaged" error!)

## Updating

```bash
brew upgrade --cask trace
```

## Uninstalling

```bash
brew uninstall --cask trace
```

To also remove application data:

```bash
brew uninstall --cask --zap trace
```

## Requirements

- macOS 12.0+ (Monterey or later)
- [Homebrew](https://brew.sh/)
