# Rescuer Locator

Offline people-tracking application for LoRaWAN-based rescue operations. Receives MGRS coordinates from RescuerBee devices via USB, stores them in PostgreSQL, and displays live positions on an interactive map.

There are a lot of things that could be done differently, but this is mostly a vibe-coded project. Due to the fact that it is not supposed to be exposed to the internet, there are a lot of compromises being done when it comes to security. 

## Prerequisites

- Python 3.11+
- Node.js 20+
- Docker + Docker Compose

## 1. Environment

```bash
cp .env.example .env
```

Open `.env` and set your passwords and serial port:

```env
POSTGRES_PASSWORD=your_password
SECRET_KEY=a_long_random_string
SERIAL_PORT=/dev/ttyUSB0   # adjust to your USB device
```

## 2. Database

```bash
cd docker
docker compose up -d
cd ..
```

The schema is applied automatically on first start.

## 3. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

pip install -r backend/requirements.txt

uvicorn backend.main:app --reload
```

API runs at **http://localhost:8000**  
Interactive API docs at **http://localhost:8000/docs**

## 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App runs at **http://localhost:5173**

## 5. First login

The backend creates a default admin on first start if no users exist.

| Username | Password |
|----------|----------|
| `admin`  | `admin`  |


## Running tests

```bash
source .venv/bin/activate
pytest backend/tests/
```

## Project structure

```
backend/        Python / FastAPI — API, WebSocket, serial reader
  serial/       USB serial parser and reader service
  routers/      REST API endpoints
  db/           PostgreSQL schema (not committed)
frontend/       Vue 3 / Vite / OpenLayers
docker/         Docker Compose for PostgreSQL + PostGIS
```
