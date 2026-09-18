# A Popup Chatbot Tutor to Scaffold Learning from Video Lectures

**Awarded 89% (First-Class Honours) — BSc Computer Science Final Year Dissertation**

A locally deployed educational AI tutor engineered to transform passive video watching into active learning. Built with Llama 3.1 8B and a custom Retrieval-Augmented Generation (RAG) pipeline, the system interrupts video lectures with adaptive knowledge checks and provides grounded, Socratic tutoring without leaking direct answers.

[**Read the full 90+ page Dissertation PDF here.**](./dissertation-report.pdf)

## System Architecture

<img width="100%" alt="System Architecture Diagram" src="https://github.com/user-attachments/assets/8acccd4e-b0f4-4187-ba2b-a43340075a31" />

*Figure 1: System Architecture detailing the RAG pipeline and component interactions (Source: Page 18).*

## Core Technical Achievements & Results

* **Adversarial Deflection (92.6%):** Engineered prompt-level guardrails that successfully deflected 92.6% of answer-extraction attempts across 54 held-out adversarial prompts derived from published prompt-hacking taxonomies.
* **Measured Learning Impact (26.3% Gain):** Conducted a within-subjects human evaluation study (N=6) demonstrating a 26.3 percentage-point mean increase in immediate retention compared to a passive video-only baseline (p = 0.016).
* **RAGAS Validation (95.7% Correctness):** Achieved a 95.7% correctness pass rate against a 47-item evaluation set, grounding model generation strictly in Stanford Encyclopedia of Philosophy entries and video transcripts.
* **ZPD-Calibrated Scaffolding Engine:** Implemented a real-time, 5-level scaffolding engine that calculates a session-scoped scalar score based on observable learner interactions (e.g., MCQ attempts, hint requests) to dynamically adjust LLM support levels from "Full Support" to "Minimal Support".

## Tech Stack

* **AI & Machine Learning:** Llama 3.1 8B Instruct (4-bit quantised), Ollama, nomic-embed-text, RAGAS framework.
* **Backend:** Python, Django REST Framework, SQLite.
* **Vector Store & Retrieval:** ChromaDB (Cosine distance metric).
* **Frontend:** React, TypeScript, Vite. 

## User Interface

<img width="100%" alt="Streamed tutor reply UI" src="https://github.com/user-attachments/assets/99705f3f-ff0a-4529-87ec-ceb2f780894d" />

*(Source: Page 37 of the report)*

The interface features an interpolated question overlay that pauses the video to serve dynamic MCQs, alongside a streaming chat panel that provides inline citations allowing users to jump directly to referenced video timestamps.

## Getting Started & Local Setup

**Note on Privacy & Copyright:** To protect participant privacy and comply with copyright, all original study databases, evaluation results, video files (`.mp4`), and transcript files (`.vtt`) have been stripped from this public repository. 

To run this project locally, you will need to supply your own media and initialise a fresh database:

1. **Environment Setup:** Create a `.env` file in the `backend/` directory and add a secure Django `SECRET_KEY`. Ensure `DEBUG = False` if deploying.
2. **Database Initialisation:** Run `python manage.py migrate` to generate a fresh local SQLite database.
3. **Adding Media:** Place your own video files in `tutor-app/public/videos/` and their corresponding transcript files in `backend/data/sep/transcripts/`.
4. **Vector Store Generation:** Run the ingestion script to fetch source documents (via `sources.json`), chunk the text, and rebuild the local ChromaDB vector store.
