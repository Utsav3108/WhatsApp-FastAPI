# API Documentation for Ripple Backend (FastAPI)

This document describes the REST API endpoints and real-time Socket.IO protocols for the Ripple mobile app backend built with FastAPI.

---

## Authentication & Security

All REST endpoints except the **Root** (`/`) and **Google Login** (`/auth/google`) endpoints require a valid Google `idToken` to be supplied as a Bearer token in the `Authorization` header:

```http
Authorization: Bearer <google_id_token>
```

The token is verified securely against Google's OAuth2 APIs. Upon validation:
- The backend matches the verified Google profile (`name`, `email`, `picture`) against a database `Persona`.
- If the persona does not exist, a new human persona is created (`is_human=True`).
- Unauthenticated requests to protected endpoints return `401 Unauthorized`.
- Attempting to access or mutate resources belonging to another user ID (such as checking another user's chat history or attempting a challenge on their behalf) returns `403 Forbidden`.

---

## Endpoints

### 1. Root (Public)
- **GET /**
- **Description:** Health check endpoint to verify backend status.
- **Response:**
  - `200 OK`: `{ "message": "FastAPI is running" }`

---

### 2. Google Login (Public)
- **POST /auth/google**
- **Description:** Authenticate, register, or login a user using a Google OAuth2 ID Token.
- **Request Body:**
  ```json
  {
    "id_token": "string"
  }
  ```
- **Response:**
  - `200 OK`: Returns the created or logged-in user's [Persona Object](#persona-object).
  - `400 Bad Request`: Validation failure if the Google ID token is invalid or expired.

---

### 3. Get All Personas (Protected)
- **GET /all-persona**
- **Description:** Get a paginated list of all personas in the database.
- **Query Parameters:**
  - `limit` (int, optional, default=50): Number of personas to return.
  - `offset` (int, optional, default=0): Pagination offset.
- **Response:**
  - `200 OK`: List of [Persona Objects](#persona-object).

#### Persona Object
- `id` (int): Unique identifier.
- `name` (string): Persona name.
- `desc` (string): Description of the persona.
- `image_url` (string): URL to their profile picture.
- `traits` (string, optional): Key traits or behaviors.
- `is_human` (bool): Indicates if the persona represents a genuine human user or an AI.

---

### 4. Search Personas (Protected)
- **GET /search-personas/{query}**
- **Description:** Search for personas by name or keyword traits.
- **Path Parameter:**
  - `query` (string): Search term.
- **Response:**
  - `200 OK`: List of [Persona Objects](#persona-object).

---

### 5. Get Personas User Chatted With (Protected)
- **GET /personas/{user_id}**
- **Description:** Get a list of personas the authenticated user has active chats with.
- **Path Parameter:**
  - `user_id` (int): User ID. Must match the authenticated `current_user.id`.
- **Response:**
  - `200 OK`: List of [Persona Objects](#persona-object).
  - `403 Forbidden`: If `user_id` does not match the authenticated user.

---

### 6. Get Messages Between Users (Protected)
- **GET /messages**
- **Description:** Retrieve chat history between the current user and another persona.
- **Query Parameters:**
  - `sender_id` (int): Sender user ID. Must match the authenticated `current_user.id`.
  - `receiver_id` (int): Receiver persona ID.
  - `limit` (int, optional, default=50): Number of messages to return.
  - `offset` (int, optional, default=0): Pagination offset.
- **Response:**
  - `200 OK`: List of Message objects.
  - `403 Forbidden`: If `sender_id` does not match the authenticated user.

#### Message Object
- `id` (int)
- `sender_id` (int)
- `receiver_id` (int)
- `text` (string)
- `image_object_name` (string, optional)
- `challenge_session_id` (int, optional)

---

### 7. Get All Challenges (Protected)
- **GET /challenges**
- **Description:** Get a list of all active challenges, each with its associated configuration and story context.
- **Response:**
  - `200 OK`: List of [Challenge Objects](#challenge-object).

#### Challenge Object
- `id` (string): Unique challenge string identifier.
- `title` (string): Title of the challenge.
- `subtitle` (string, optional)
- `description` (string, optional)
- `short_description` (string, optional)
- `categories` (list of string, optional)
- `suggested_personas` (list of int, optional)
- `difficulty` (string, optional: "beginner", "intermediate", "advance")
- `difficulty_settings` (dict, optional)
- `estimated_duration_minutes` (int, optional)
- `challenge_rules` (dict, optional)
- `image_url` (string, optional)
- `selected_persona_id` (int, optional)
- `context` (ChallengeContext object, optional)

#### ChallengeContext Object
- `id` (int)
- `challenge_id` (string)
- `setting` (string)
- `environment` (object, optional)
- `goal` (string)
- `stakes` (string)
- `platform` (string)

---

### 8. Create or Update Challenge (Protected)
- **POST /challenges**
- **Description:** Create a new challenge configuration or update an existing one.
- **Request Body:** ChallengeCreate object
- **Response:**
  - `200 OK`: [Challenge Object](#challenge-object).

---

### 9. Setup Challenge (Protected)
- **POST /setup_challenge**
- **Description:** Start or resume a challenge session with a selected AI persona. If a session is active, returns the existing context; otherwise, assigns the persona and generates the starting storyline.
- **Request Body:**
  - `challenge_id` (string): The challenge to start.
  - `user_id` (int): The user ID. Must match the authenticated `current_user.id`.
  - `persona_id` (int, optional): Persona to assign.
  - `attempt_session_id` (int, optional): Links to a specific previous attempt session if retrieving logs.
- **Response:**
  - `200 OK`: ChallengeSetupResponse object.
  - `403 Forbidden`: If `user_id` does not match the authenticated user.

#### ChallengeSetupResponse Object
- `message` (string)
- `challenge_session_id` (int, optional): Unique session ID.
- `intro` (StorylineResponse object, optional): Contains `storyline` and `call_to_action`.
- `status` (string, optional): Current challenge state (e.g. `active`, `won`, `lost_rejected`).
- `total_duration_minutes` (int, optional)
- `conversation_history` (array of Message objects, optional)

---

### 10. Get Challenge Attempts (Protected)
- **GET /challenge-attempts/{challenge_id}**
- **Description:** Get the attempt history of the **currently authenticated user** for the specified challenge. Attempts by other users are excluded.
- **Path Parameter:**
  - `challenge_id` (string): Challenge ID.
- **Response:**
  - `200 OK`: List of ChallengeAttempt objects.

#### ChallengeAttempt Object
- `id` (UUID): Unique attempt ID.
- `challenge_id` (string)
- `user_id` (int): User ID.
- `persona_id` (int): Target AI persona.
- `role_mode` (string, optional)
- `won` (bool): Win outcome flag.
- `time_taken_seconds` (int, optional)
- `attempt_number` (int, optional)
- `created_at` (string, datetime)

---

## Real-Time Messaging (Socket.IO)

- **Socket.IO Endpoint:** `/socket.io`
- Protocol events, room joining, and server events remain unchanged. Refer to [socketio_server_events.md](file:///Users/utsav/Documents/Projects/WhatsApp/app/docs/socketio_server_events.md) for Socket.IO API schemas.
