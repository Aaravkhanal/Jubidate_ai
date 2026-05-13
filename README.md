<div align="center">
  <h1>🌌 Jubidate AI</h1>
  <h3>Multi-Agent Strategic Intelligence Platform</h3>

  <p>
    <img src="https://img.shields.io/badge/Next.js-000000?style=for-the-badge&logo=next.js&logoColor=white" alt="Next.js" />
    <img src="https://img.shields.io/badge/TypeScript-3178C6?style=for-the-badge&logo=typescript&logoColor=white" alt="TypeScript" />
    <img src="https://img.shields.io/badge/Gemini-8E75B2?style=for-the-badge&logo=google&logoColor=white" alt="Gemini" />
    <img src="https://img.shields.io/badge/Groq-F55036?style=for-the-badge&logo=groq&logoColor=white" alt="Groq" />
    <img src="https://img.shields.io/badge/OpenRouter-000000?style=for-the-badge&logo=openrouter&logoColor=white" alt="OpenRouter" />
    <img src="https://img.shields.io/badge/Tailwind_CSS-38B2AC?style=for-the-badge&logo=tailwind-css&logoColor=white" alt="Tailwind CSS" />
    <img src="https://img.shields.io/badge/Vercel-000000?style=for-the-badge&logo=vercel&logoColor=white" alt="Vercel" />
    <img src="https://img.shields.io/badge/AI_Agents-000000?style=for-the-badge&logo=openai&logoColor=white" alt="AI Agents" />
    <img src="https://img.shields.io/badge/Voice_AI-FF4F00?style=for-the-badge&logo=google&logoColor=white" alt="Voice AI" />
  </p>

  <p><b>A futuristic AI strategic operating system for alignment simulations and advanced multi-model orchestration.</b></p>
</div>

---

## 📖 Overview

Jubidate AI is a production-grade, multi-agent orchestration platform that brings advanced Strategic Intelligence to life. Moving beyond simple AI chats, Jubidate AI runs **Alignment Simulations** where multiple specialized AI models collaborate, synthesize, and reason through complex objectives in real-time. 

With full support for **high-fidelity Speech-to-Text (STT) and Text-to-Speech (TTS)**, Jubidate AI acts as a cinematic AI command center, delivering hands-free strategic orchestration.

## ✨ Features

- **Multi-Agent Orchestration**: Spin up clusters of specialized AI roles (Researchers, Advocates, Critics, Judges) running concurrently on different LLMs.
- **Voice Interaction (TTS & STT)**: Real-time, provider-agnostic voice engine utilizing Google Cloud's premium generative voice models. Connect with agents via full-duplex speech-to-speech interaction.
- **Strategic Intelligence System**: Automatically audits logical consistency, generates strategic flowcharts, and provides actionable intelligence from every reasoning layer.
- **Alignment Simulations**: Run both Autonomous (AI vs AI) and Human-in-the-loop (Human vs AI) alignment simulations to explore strategic solutions.
- **Real-Time AI Reasoning**: Watch agent reasoning streams live via WebSocket data streaming.

## 🏗 Architecture

Jubidate AI is built on a split architecture ensuring rapid inference and optimal UI performance.

- **Frontend**: Next.js 15 (App Router), React 19, Tailwind CSS, Framer Motion for cinematic micro-animations.
- **Backend**: FastAPI (Python), utilizing LiteLLM for routing requests to 100+ different AI models.
- **Communication**: Full-duplex WebSocket architecture for streaming tokens and binary audio chunks simultaneously.
- **Storage**: Local SQLite via SQLAlchemy (Zero external DB dependencies).

## 🧠 Multi-Agent Orchestration & Strategy Nodes

Instead of a single LLM trying to solve a problem, Jubidate AI uses a graph of **Strategy Nodes**.
1. **Advocates**: Frame the strategic narrative.
2. **Researchers**: Pull real-time data and evidence.
3. **Critics**: Pressure-test hypotheses to find logical flaws.
4. **Examiners**: Cross-examine data sources for validity.
5. **System Auditor (Judge)**: Synthesizes the final strategic objective and scores the reasoning layer.

## 🎙 Voice Interaction (Speech-to-Speech)

We have deeply integrated Google's **Text-to-Speech (TTS) and Speech-to-Text (STT)** APIs directly into the Strategic OS. 
- You can communicate with the command center entirely hands-free.
- High-fidelity voice responses ensure natural cadence and intonation from the Strategy Nodes.

## 🔌 AI Providers Integrated

- **Google Gemini**: Native integration for multimodal reasoning and STT/TTS.
- **Llama via Groq**: For ultra-fast, low-latency conversational reasoning.
- **MiniMax**: Advanced alignment and contextual analysis.
- **Kimi via Fireworks**: Rapid strategy generation.
- **OpenRouter**: Access to the entire open-source ecosystem (DeepSeek, Llama-3, etc).

## 🚀 Deployment

The project is deployment-ready with no hardcoded localhost dependencies.

### Environment Setup
Copy `.env.example` to `.env` and fill in your keys:
```bash
cp .env.example .env
```

### Run Locally (Development)
Ensure you have `python` and `Node.js` installed.
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
npm install --prefix frontend

# Start the cinematic OS (Frontend & Backend simultaneously)
python dev.py
```

### Production Build
```bash
# Build the Next.js static assets
npm run build --prefix frontend

# Start production server
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

## 🔒 Security

- **API Keys**: All LLM and Cloud API keys are securely managed entirely on the backend server side. 
- **Secret Management**: Verified `.gitignore` ensures zero accidental credential leakage.
- **No External Dependencies**: Database is completely local, ensuring maximum privacy for enterprise strategies.

## 🔮 Future Scope

- **Continuous Strategy Loops**: Agents that stay active for days to monitor changing world conditions.
- **Multimodal Strategic Nodes**: Incorporating visual and document analysis directly into the alignment simulations.
- **Enterprise SSO**: SAML and generic SSO integration for secure corporate strategy centers.

---
*Built with precision for the future of AI Strategic Analysis.*
