# 🧠 NUS Compass

An AI agent that optimizes a student's entire university trajectory — built for the SimplifyNext 2026 Agentic AI Hackathon.

**This isn't just a pitch — it's a working full-stack app.** FastAPI + LangGraph backend (5 linear graphs, one shared state), React frontend, real NUSMods module/prerequisite data (727 modules, live-fetched), Groq-hosted LLM for trajectory generation, leverage-move ranking, and outreach drafting.

- **Run it**: [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md) — one command (`run_dev.py`) starts both servers; the only thing you need to supply is a free Groq API key.
- **How it's built**: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — data pipeline, agent graphs, storage, endpoints.
- **What's real vs. synthetic**: the NUS module catalog and prerequisite graph are real, live NUSMods data; professors, internships, competitions, scholarships, and alumni stories are a small hand-authored synthetic dataset (see [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md#whats-real-vs-synthetic)) — no real people or companies.

