# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — 2025-10-23

### Added

- Multi-provider LLM router with fallback chain (primary → secondary → tertiary).
- Provider implementations: Anthropic, OpenAI, Ollama (local).
- Provider Protocol pattern for testable dependency injection.
- Response cache (in-memory LRU with TTL).
- Budget tracker (token in/out, cost) with enforcement.
- Per-provider retry with tenacity (exponential backoff).
- Structured logging with provider, latency, tokens, and cost on every call.
- AllProvidersFailed aggregate error when every provider fails.
- Unit tests: happy path, fallback, cache-hit, all-fail, budget exceed, timeout.