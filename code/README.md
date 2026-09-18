# Project Setup Instructions

First, extract the ZIP file and open the project folder in VS Code.

## 1. LLM Setup (Ollama)
*Note: Start Ollama first, as it needs to be running in the background if you have to rebuild the databases.*

Open a terminal and start Ollama:
```bash
ollama serve
```

Open a second terminal and install the required models:
```bash
ollama pull nomic-embed-text
ollama pull llama3.1:8b-instruct-q4_K_M
```

## 2. Backend Setup
Open a terminal and navigate to the backend directory:
```bash
cd backend
uv sync
```

### Scenario A: Databases are NOT missing
If your `sqlite3` databases are present, simply start the server:
```bash
uv run python manage.py runserver
```

### Scenario B: Databases ARE missing
If your databases are missing, you need to migrate and ingest data:
```bash
uv run python manage.py migrate
```
*Note: Ensure Ollama is serving `nomic-embed-text` before running the ingest step (this is required if the `chroma.sqlite3` db is missing).*
```bash
uv run python manage.py ingest
uv run python manage.py runserver
```

## 3. Frontend Setup
Open a new terminal and navigate to the frontend app:
```bash
cd tutor-app
npm install
npm run dev
```
Once the server starts, click the `localhost` link shown in the terminal to view the application.

---

## Troubleshooting & Notes
* **Missing Videos:** If videos are missing from the project, they need to be placed in the following directory: `tutor-app\public\videos`
