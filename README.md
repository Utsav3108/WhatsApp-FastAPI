
# WhatsApp AI Chat Backend

A FastAPI-based backend for a WhatsApp-like chat application, featuring AI-powered responses from historical presidents using Google Gemini. Now with **Socket.IO** for real-time chat, replacing the legacy FastAPI WebSocket endpoint. This project demonstrates clean architecture, modular code, and modern Python best practices.


## Features

- **FastAPI**: High-performance Python web framework for APIs
- **Socket.IO Real-Time Chat**: Modern, robust real-time communication using Socket.IO (see `socketio_server.py`)
- **AI Integration**: Uses Google Gemini to generate responses as historical presidents
- **SQLite + SQLAlchemy**: Simple, reliable database and ORM
- **Pydantic**: Data validation and serialization
- **Modular Structure**: Clean separation of routes, business logic, models, and schemas

## Project Structure

```
app/
  main.py            # FastAPI app entrypoint, lifespan event for startup
   routes.py          # All REST API routes
   socketio_server.py # Socket.IO event handlers (real-time chat)
  crud.py            # Business logic and DB operations
  database.py        # SQLAlchemy setup
  models.py          # ORM models
  schemas.py         # Pydantic schemas
  gemini.py          # Google Gemini AI integration
   websocket.py       # (Legacy) WebSocket helpers (no longer used)
  data.json          # Initial data for presidents
   AppServices/
      connection_manageer.py # Connection manager for real-time users
```

## Quick Start

1. **Clone the repo**
   ```bash
   git clone https://github.com/yourusername/WhatsApp-FastAPI.git
   cd whatsapp-ai-chat-backend
   ```

## Docker Quick Start

You can run the backend and Redis with Docker Compose. This will automatically set up persistent volumes for your app data and Redis.

1. **Create a `.env` file in the project root** (for environment variables, e.g. API keys):
   ```env
   GEMINI_API_KEY=your_gemini_api_key_here
   # Add other environment variables as needed
   ```

2. **Build and start the services:**
   ```bash
   docker-compose up --build
   ```

3. **Access the API docs:**
   - Open [http://localhost:8000/docs](http://localhost:8000/docs)

4. **Persistent Data:**
   - App data is stored in a Docker volume and mapped to `app/data` inside the container.
   - Redis data is also persisted in a Docker volume.

5. **Stopping services:**
   ```bash
   docker-compose down
   ```

---
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

## Real-Time Chat (Socket.IO)

The backend now uses **Socket.IO** for real-time chat. Connect your client to:

- **Socket.IO endpoint:** `ws://localhost:8000/socket.io/`

### Example Socket.IO Events

- `join` — Register a user session:
  ```js
  socket.emit('join', { user_id: 123 });
  ```
- `send_message` — Send a chat message:
  ```js
  socket.emit('send_message', { sender_id: 123, receiver_id: 456, text: "Hello!" });
  ```
- `receive_message` — Receive messages (including AI responses):
  ```js
  socket.on('receive_message', (msg) => { console.log(msg); });
  ```

See `app/socketio_server.py` for all event logic.


## API Overview

- `GET /presidents/{user_id}` — List all presidents a user has chatted with
- `GET /messages` — Get messages between users
- **Real-time chat:** Use Socket.IO events (see above)


## Customization
- Add or modify presidents in `data.json`
- Extend AI logic in `gemini.py`
- Add new REST routes in `routes.py`
- Add/modify real-time events in `socketio_server.py`

## License

MIT License. See [LICENSE](LICENSE) for details.

---


*Built with FastAPI, Socket.IO, SQLAlchemy, and Google Gemini AI.*

---

## Docker Compose Overview

- **FastAPI app** runs in a container, exposing port 8000
- **Redis** runs in a container (using `redis/redis-stack`), exposing port 6379
- **Persistent volumes** for both app data and Redis data
- **Environment variables** are injected from your `.env` file

See `docker-compose.yml` and `Dockerfile` in the project root for details.
