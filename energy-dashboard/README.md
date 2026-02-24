# Energy Market Dashboard

Extracts from a production energy market dashboard providing real-time spot price analysis for the Chilean electricity grid. The full application visualizes hourly marginal costs across 500+ grid nodes, with scenario comparison, temporal pattern analysis, and geographic mapping.

This sample contains the most architecturally interesting components: the Dash application factory, the complete enterprise security module, and the data processing layer.

## Architecture

### Multi-Page Dash Application (`dashboard/`)
- **`app.py`** -- Application factory with Prometheus middleware, optional authentication, health/readiness endpoints (`/healthz`, `/metrics`), background data preloading, and multi-page validation layout supporting 11 analytical views
- **`router.py`** -- Client-side URL routing callback mapping pathnames to page layouts (overview, explorer, temporal patterns, scenario comparison, risk distribution, correlations, geographic map, etc.)

### Enterprise Security Module (`security/`)
Full OWASP Top 10 implementation with defense-in-depth:
- **`__init__.py`** -- Security orchestrator with sensible defaults for all modules (rate limiting, headers, session, audit, IP protection, CSRF)
- **`rate_limiter.py`** -- Thread-safe in-memory rate limiter with dual-key login protection (per-IP + per-username), progressive blocking, Redis backend support, and `@rate_limit` decorator
- **`audit_logger.py`** -- Structured security audit logging with 30+ event types, SIEM-compatible JSON output, automatic request context capture, and `@audit_endpoint` decorator
- **`session.py`** -- Secure session management with concurrent session limits, idle/absolute timeouts, fingerprint-based hijacking detection, and automatic session rotation on login
- **`headers.py`** -- OWASP security headers middleware: CSP (tuned for Dash/Plotly), HSTS, X-Frame-Options, Permissions-Policy, cache control for sensitive paths
- **`csrf.py`** -- CSRF protection with HMAC-signed tokens, double-submit cookie pattern, Origin/Referer validation
- **`ip_protection.py`** -- IP whitelist/blacklist, automatic suspicious behavior detection, progressive auto-blocking, proxy header parsing (X-Forwarded-For, CF-Connecting-IP)
- **`password_policy.py`** -- NIST 800-63B compliant password policy: complexity rules, common password detection, keyboard pattern detection, leet-speak normalization, Have I Been Pwned integration
- **`totp.py`** -- RFC 6238 TOTP two-factor authentication: Google Authenticator compatible, QR code generation, one-time backup codes with secure hash storage

### Data Processing Layer (`data_processing/`)
- **`smart_cache.py`** -- Hybrid LRU memory + disk cache with TTL invalidation, Arrow IPC + LZ4 serialization, automatic disk cleanup, and `@cached` decorator
- **`data_loader.py`** -- Centralized data loader with parallel Arrow file scanning via ThreadPoolExecutor, Polars LazyFrame concatenation, filter-before-join optimization, and singleton pattern
- **`downsampling.py`** -- LTTB (Largest Triangle Three Buckets) algorithm for time series visualization: O(n) complexity, preserves visual features, supports Polars/Pandas/NumPy, adaptive threshold selection
- **`metrics.py`** -- Prometheus instrumentation: HTTP request histograms, cache hit/miss counters, data loading duration, application health gauges, `@timed` decorator

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Dashboard | Dash 2.x, Plotly, Flask |
| Data processing | Polars (LazyFrame), Apache Arrow IPC |
| Authentication | Flask-Login, SQLAlchemy, Argon2id |
| 2FA | pyotp (TOTP), QR code generation |
| Monitoring | prometheus_client, structured logging |
| Caching | Custom LRU + disk (Arrow IPC + LZ4) |
| Deployment | Docker, Gunicorn, NGINX |

## Key Patterns

- **Application factory** (`create_app()`) for testability and configuration flexibility
- **Validation layout** for multi-page Dash apps to prevent client-side callback errors
- **Filter-before-join** optimization reducing join cardinality by 10-100x
- **Parallel file scanning** with adaptive thread pool sizing
- **Defense-in-depth security** with layered protections (rate limit -> IP check -> auth -> CSRF -> audit)
- **Graceful degradation** (Redis -> memory fallback, prometheus optional, security modules independent)

## Note

This is a curated extract. The full production system includes 11 analytical pages, 80+ callbacks, geographic visualization with Mapbox, scenario comparison tools, and automated data pipelines. Internal identifiers, credentials, and proprietary data references have been removed.
