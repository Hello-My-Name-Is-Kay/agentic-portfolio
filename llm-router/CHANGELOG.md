# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `providers/ollama.py` had a syntax error in its log call; the package could not be imported.
- Retries only covered timeouts, and the `max_retries` argument was ignored (always 3 attempts). Connection errors, HTTP 429 and 5xx are now retried too, `max_retries` is honoured, and 4xx errors are not retried.
- The budget raised only after a call had been made, so calls kept being made once it was exceeded. Calls are now refused before reaching a provider once a limit is reached.
- Cache hits were returned with `cached=False`.
- Re-caching an existing key in a full cache evicted an unrelated entry.
- Logs went to stdout, so `--json` output was not parseable. They now go to stderr.
- The CLI ignored the API keys in settings and only ever called Ollama.

### Changed

- Exceptions renamed with an `Error` suffix (`AllProvidersFailedError`, `BudgetExceededError`, `ProviderTimeoutError`); `RetryableProviderError` added. The unused `RetryBudgetExhausted` was removed.
- Shared HTTP and retry code moved to `providers/_http.py`; providers accept a `transport` for testing and per-token cost rates.

### Added

- Provider tests against mocked HTTP, CLI tests, and budget/cache edge-case tests.

## [0.1.0] — 2025-10-23

### Added

- Router with fallback chain, Anthropic/OpenAI/Ollama providers, LRU cache, budget tracker, CLI.
