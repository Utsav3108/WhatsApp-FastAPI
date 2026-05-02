# WhatsApp AI Chat Backend

A FastAPI-based backend for a WhatsApp-like chat application, featuring AI-powered responses from historical presidents using Google Gemini. This project demonstrates clean architecture, modular code, and modern Python best practices.

## Features

- **FastAPI**: High-performance Python web framework for APIs and WebSockets
- **WebSocket Support**: Real-time chat with user-to-user and AI persona messaging
- **AI Integration**: Uses Google Gemini to generate responses as historical presidents
- **SQLite + SQLAlchemy**: Simple, reliable database and ORM
- **Pydantic**: Data validation and serialization
- **Modular Structure**: Clean separation of routes, business logic, models, and schemas

## Project Structure

```
app/
  main.py            # FastAPI app entrypoint, lifespan event for startup
  routes.py          # All API and WebSocket routes
  crud.py            # Business logic and DB operations
  database.py        # SQLAlchemy setup
  models.py          # ORM models
  schemas.py         # Pydantic schemas
  gemini.py          # Google Gemini AI integration
  websocket.py       # (Legacy) WebSocket helpers
  data.json          # Initial data for presidents
  AppServices/
    connection_manageer.py # WebSocket connection manager
```

## Quick Start

1. **Clone the repo**
   ```bash
   git clone https://github.com/yourusername/whatsapp-ai-chat-backend.git
   cd whatsapp-ai-chat-backend/app
   ```
2. **Create and activate a virtual environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```
3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```
4. **Set up environment variables**
   - Create a `.env` file with your Google Gemini API key:
     ```env
     GEMINI_API_KEY=your_gemini_api_key_here
     ```
5. **Run the server**
   ```bash
   uvicorn app.main:api --reload
   ```
6. **Access the API docs**
   - Open [http://localhost:8000/docs](http://localhost:8000/docs)

## API Overview

- `GET /presidents` — List all presidents
- `POST /messages` — Send a message
- `GET /messages` — Get messages between users
- `WebSocket /ws/{user_id}` — Real-time chat

## Customization
- Add or modify presidents in `data.json`
- Extend AI logic in `gemini.py`
- Add new routes in `routes.py`

## License

MIT License. See [LICENSE](LICENSE) for details.

---

*Built with FastAPI, SQLAlchemy, and Google Gemini AI.*
