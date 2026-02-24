# Portfolio Samples

Selected extracts from production systems totaling **1M+ lines of code** across Python, C++20, Fortran, and TypeScript.

Each folder contains real code from a larger project, with a README explaining the full scope and what the sample demonstrates.

---

## Projects

### [sddp-solver/](./sddp-solver)
**Stochastic Dual Dynamic Programming solver for the Chilean electricity market**

Re-engineered a production SDDP hydrothermal dispatch solver. 108K+ LOC across Fortran, C++, and Python/Pyomo. Reduced a critical subroutine from O(n³) to O(n²), unlocking 10-50x speedup potential.

`Python` · `Pyomo` · `CPLEX` · `Gurobi` · `NumPy` · `pytest`

---

### [hft-engine/](./hft-engine)
**High-frequency trading engine with sub-millisecond ML inference**

C++20 quantitative trading engine with ONNX Runtime inference, lock-free ring buffers, SIMD-optimized feature computation, and ZeroMQ messaging. Includes a Python ML pipeline with Optuna hyperparameter optimization and LightGBM.

`C++20` · `ONNX Runtime` · `ZeroMQ` · `Apache Arrow` · `LightGBM` · `Optuna`

---

### [electria-saas/](./electria-saas)
**AI-powered SaaS assistant for LATAM electricity markets (work in progress)**

Multi-country SaaS platform with RAG-based chat, regulatory alerts, and market dashboards. FastAPI backend with Claude API + LlamaIndex, Next.js frontend with Tailwind CSS.

`FastAPI` · `Next.js` · `Claude API` · `LlamaIndex` · `Pinecone` · `Supabase` · `Stripe`

---

### [energy-dashboard/](./energy-dashboard)
**Production dashboard for electricity market monitoring**

Multi-page Dash application with real-time data visualization, Prometheus metrics, and a full security module (TOTP, CSRF, rate limiting, audit logging). Handles 500+ grid nodes with smart caching and downsampling.

`Dash` · `Polars` · `Apache Arrow` · `Flask` · `Prometheus` · `Docker`

---

### [etl-pipeline/](./etl-pipeline)
**Parallel data ingestion and transformation pipelines**

Production ETL pipelines processing electricity market data from multiple sources (CEN, XM, CENACE, REE). Parallel CSV/Parquet ingestion with ThreadPoolExecutor, Polars transformations, and Arrow-based scanning.

`Python` · `Polars` · `Apache Arrow` · `ThreadPoolExecutor` · `aiohttp`

---

## About

These samples are extracts from 23 production systems I have built and maintained. They demonstrate:

- **Mathematical optimization** — SDDP, Benders decomposition, MILP, Unit Commitment
- **High-performance computing** — C++20, SIMD, lock-free data structures, sub-ms latency
- **Full-stack development** — FastAPI, React/Next.js, PostgreSQL, Docker
- **Data engineering** — Polars, Apache Arrow, parallel I/O, ETL pipelines
- **ML engineering** — ONNX Runtime, LightGBM, Optuna, feature stores
- **Security** — TOTP, CSRF protection, rate limiting, WAF, audit logging

All code is tested (80-95% coverage), containerized (Docker, GitHub Actions CI), and built to be handed off cleanly.

## Contact

Andres Zapata Barrientos
- [LinkedIn](https://www.linkedin.com/in/andrészapata-barrientos)
