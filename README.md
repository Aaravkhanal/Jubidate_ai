<div align="center">

# 🌌 JUBIDATE | Strategic Intelligence OS

[![Next.js 15](https://img.shields.io/badge/Next.js-15-black?style=for-the-badge&logo=next.js)](#)
[![React 19](https://img.shields.io/badge/React-19-20232A?style=for-the-badge&logo=react)](#)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi)](#)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind-38B2AC?style=for-the-badge&logo=tailwind-css)](#)
[![NVIDIA NIM](https://img.shields.io/badge/NVIDIA-NIM-76B900?style=for-the-badge&logo=nvidia)](#)

*Jubidate is a next-generation AI orchestration platform that moves beyond single-turn chatbots. It coordinates multiple specialized AI models to debate, challenge, and synthesize complex strategic outcomes in real-time.*

</div>

---

## 📖 Table of Contents
- [Project Vision](#-project-vision)
- [Live Demo](#-live-demo)
- [Platform Showcase](#-platform-showcase)
- [Core Architecture](#-core-architecture)
- [How It Works](#-how-it-works-the-node-system)
- [Quick Start Guide](#-quick-start-guide)
- [Deployment Configuration](#-deployment-configuration)

---

## 🔭 Project Vision
Most AI applications today operate as basic question-and-answer interfaces. **Jubidate** introduces a "Command Center" paradigm where users don't just chat with AI—they **orchestrate it**. By assigning distinct roles (e.g., Pro Advocate, Con Advocate, Judge, and Auditor) to multiple models simultaneously, the platform delivers rigorous, multi-faceted analysis for any strategic prompt.

This project was built to demonstrate advanced full-stack engineering, robust WebSockets integration, complex UI/UX state management, and an innovative approach to AI alignment.

---

## 🚀 Live Demo
- **Frontend App:** [https://jubidate-ai.vercel.app](https://jubidate-ai.vercel.app)
- **Backend API (Swagger):** [https://jubidateai-production.up.railway.app/docs](https://jubidateai-production.up.railway.app/docs)

---

## 📸 Platform Showcase

### 1. Neural Orchestration & Strategy Sessions
> **Screenshot Suggestion:** *Add an image of the main Debate UI showing the Judge's Verdict and the Pro/Con arguments.*

<img src="https://via.placeholder.com/800x450.png?text=Strategy+Session+Dashboard" width="800" alt="Strategy Session Dashboard" />

*The Strategy Session UI where multiple AI agents debate in real-time. The interface clearly separates the arguments from the Pro side, Con side, and the final ruling from the Supreme Adjudicator.*

### 2. Autonomous Adjudication
> **Screenshot Suggestion:** *Add an image showing the "Statistics the Judge Should Consider" and "Evidence Quality Warnings" sections.*

<img src="https://via.placeholder.com/800x450.png?text=Judge+Analytics+Panel" width="800" alt="Judge Analytics Panel" />

*The Judge agent synthesizes arguments, highlights "Best Affirmative" and "Best Skeptical" points, and identifies gaps in reasoning or areas requiring further empirical evidence.*

### 3. Agent Memory & System Core
> **Screenshot Suggestion:** *Add an image of the sidebar panels like Matrix Overview, Agent Memory, or Command Center.*

<img src="https://via.placeholder.com/800x450.png?text=Agent+Memory+and+Matrix" width="800" alt="Agent Memory" />

*Tracks the cognitive flow, tracks agent experiences, and allows for deep customization of the debate rounds and intelligence parameters.*

---

## ⚙️ Core Architecture
Built with a strict separation of concerns to handle high-frequency WebSocket streams and complex frontend states seamlessly.

- **Frontend:** Next.js 15, React 19, Tailwind CSS, TypeScript, Framer Motion
- **Backend:** FastAPI, Python, WebSockets, LiteLLM
- **Database:** SQLite (with structured JSON schemas for session logs and intelligence records)
- **Orchestration Engine:** Manages turn-based and concurrent generation streams dynamically.
- **AI Integration:** NVIDIA NIM (Llama 3.1 70B, Nemotron, Mixtral, etc.) + Google Gemini / Groq / OpenRouter compatibility.

---

## 🧠 How It Works: The Node System
Instead of a single LLM call, Jubidate routes a user query through a configured multi-agent pipeline:

1. **Initialize:** The user sets the strategic objective (e.g., "The impact of practical skills vs theoretical foundations in education").
2. **Assign:** Models are dynamically assigned to the `Pro Side` and `Con Side`. An isolated `Judge` model is instantiated.
3. **Debate:** The advocates construct arguments, pressure-test each other, and identify flaws via multi-turn WebSocket streaming.
4. **Adjudicate:** The Judge analyzes the cognitive clusters, declares a winner, and outputs an actionable "Strategic Summary" containing evidence quality warnings and unanswered points.

---

## 💻 Quick Start Guide

### Prerequisites
- Node.js (v18+)
- Python (v3.10+)
- An NVIDIA API Key

### 1. Backend Setup
```bash
git clone https://github.com/Aaravkhanal/Jubidate_ai.git
cd Jubidate_ai/backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows use `\.venv\Scripts\activate`

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env 
# -> Open .env and add your NVIDIA_API_KEY

# Run server
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 2. Frontend Setup
```bash
cd ../frontend

# Install dependencies
npm install

# Configure environment
cp .env.example .env.local
# -> Open .env.local and set NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
# -> Set NEXT_PUBLIC_WS_BASE_URL=ws://localhost:8000

# Run development server
npm run dev
```

---

## 🌐 Deployment Configuration

### Vercel (Frontend)
Ensure the following environment variables are set to point to your backend:
- `NEXT_PUBLIC_API_BASE_URL` (e.g., `https://your-backend.up.railway.app`)
- `NEXT_PUBLIC_WS_BASE_URL` (e.g., `wss://your-backend.up.railway.app`)

### Railway (Backend)
- Add your `NVIDIA_API_KEY` (and any other provider keys) to the Railway Environment Variables.
- The included `railway.toml` handles the Nixpacks build and Uvicorn startup automatically.

---
<div align="center">
<i>Built to demonstrate advanced AI orchestration, real-time WebSocket communication, and premium UI/UX design.</i>
</div>
