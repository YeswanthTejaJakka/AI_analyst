# QueryPilot — AI-Powered Natural-Language Database Analyst

QueryPilot is a production-quality conversational AI application that allows users to query relational databases using natural language. Rather than naively converting text into SQL, QueryPilot automatically understands database schemas, detects ambiguity in user requests, asks targeted clarification questions when necessary, generates safe SQL, executes it, and explains the results.

---

## 🌟 Core Architecture & Pipeline Flow

The central philosophy of QueryPilot is that **an LLM should never directly execute SQL against a database without intent validation and safety guardrails**.

```
Natural Language Query
         ↓
Intent Extraction & Context Tracking
         ↓
Schema Introspection & Retrieval
         ↓
Ambiguity Detection Engine
  ┌───────────────┴───────────────┐
  ▼                               ▼
Ambiguous                       Clear
  │                               │
Clarification Question           SQL Generator
(Clickable options + Custom)       │
  │                               ▼
  └───────────────┬───────────────┘
                  ▼
          SQL Safety Validator
          (Read-only, AST scan, No DROP/DELETE/INSERT/UPDATE)
                  ↓
          Query Cost Protection
          (Row limit injection & Timeout caps)
                  ↓
          Database Execution
                  ↓
       Result Processing & Table Rendering
                  ↓
      Natural Language Result Explanation
```

---

## 🔍 Ambiguity Detection Engine

Natural language queries are frequently underspecified. QueryPilot detects multiple categories of ambiguity:

1. **Metric Ambiguity**: *"Who is our best customer?"* → Asks whether "best" means highest total spending, most orders, most products purchased, or highest average order value.
2. **Time Ambiguity**: *"Show recent sales."* → Asks whether "recent" means last 7 days, 30 days, 90 days, or current year.
3. **Threshold Ambiguity**: *"Find expensive products."* → Asks whether "expensive" means price > ₹10,000, price > average price, or top 10% price.
4. **Entity / Business Term Ambiguity**: Identifies missing schema tables and explains why a query cannot be answered rather than hallucinating table names.

---

## 💾 Database Connection Modes

QueryPilot supports three connection modes:

### Mode A — Built-in Sample Database (Default)
Connects instantly to a pre-populated e-commerce database with zero user credentials required:
- `customers` (1,000+ records)
- `orders` (5,000+ records)
- `order_items` (10,000+ records)
- `products` (500+ records)
- `categories` (20+ records)

### Mode B — SQLite Database Upload
Users can upload any `.db` SQLite file up to 50 MB. The backend validates the database, introspects its tables, columns, data types, primary keys, and foreign keys, creates an isolated session, and cleans up temporary files upon session deletion.

### Mode C — Remote PostgreSQL Connection
Connect to external PostgreSQL instances using standard host, port, database, username, password, and SSL parameters.
> [!IMPORTANT]
> **Localhost Limitation**: Browser access to a cloud-deployed QueryPilot backend cannot directly reach `localhost:5432` on the user's local workstation. The interface explicitly guides users to upload an SQLite file, connect a publicly accessible PostgreSQL instance, or run QueryPilot locally via Docker.

---

## 🛡️ Security & SQL Protection Model

1. **Strict Read-Only Operations**: Only `SELECT` and `WITH` statements are permitted. Destructive SQL commands (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `ALTER`, `TRUNCATE`, `CREATE`, `GRANT`, `REVOKE`, etc.) are actively blocked.
2. **AST & Lexical Token Scanning**: Uses `sqlparse` to disallow stacked statement execution (e.g. `SELECT 1; DROP TABLE users;`).
3. **Schema Table Verification**: Verifies table names in `FROM` and `JOIN` clauses against actual introspected schema metadata.
4. **Row Count & Execution Timeout Caps**: Automatically injects `LIMIT` clauses to prevent memory exhaustion and sets database query timeouts.
5. **Credential Protection**: Database passwords are never logged, stored on disk, or exposed in error messages.

---

## 🛠️ Technology Stack

- **Frontend**: React 18, TypeScript, Vite, Tailwind CSS v4, Lucide Icons
- **Backend**: Python 3.12, FastAPI, Pydantic v2, SQLAlchemy, sqlparse
- **Databases**: SQLite, PostgreSQL
- **Containerization**: Docker, Docker Compose, Nginx

---

## 🚀 Quick Start (Local Setup)

### Option 1: Docker Compose (Recommended)

```bash
docker-compose up --build
```
- Frontend UI: `http://localhost:3000`
- Backend API Docs: `http://localhost:8000/docs`

---

### Option 2: Manual Local Setup

#### Backend Setup

```bash
cd backend
python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```
Open `http://localhost:3000` in your browser.

---

## 🧪 Testing

QueryPilot includes full automated unit and integration tests covering the complete critical acceptance test suite:

```bash
cd backend
.\venv\Scripts\pytest -v
```

### Test Coverage Highlights:
- **Test 1**: Simple query count (`How many customers are there?`)
- **Test 2**: Multi-table join (`Which customer spent the most?`)
- **Test 3**: Ambiguity detection (`Who is the best customer?`)
- **Test 4**: Time ambiguity (`Show recent customers.`)
- **Test 5**: Dangerous query rejection (`Delete all customers.`)
- **Test 6**: Contextual follow-up (`Show top 5 customers by spending` → `What about the second one?`)
- **Test 7**: Unknown entity handling (`Show our most profitable suppliers.`)
- **Test 8**: Sample database instant connection
- **Test 9**: SQLite file upload introspection
- **Test 10**: Read-only protection enforcement

---

## 📐 Project Structure

```
querypilot/
├── backend/
│   ├── app/
│   │   ├── adapters/          # Database adapters (SQLite, PostgreSQL)
│   │   ├── api/               # FastAPI route handlers (chat, database)
│   │   ├── core/              # Config & settings
│   │   ├── models/            # Pydantic data schemas (Schema, Chat, Intent)
│   │   ├── services/
│   │   │   ├── ai/            # Provider abstractions (Heuristic, Gemini, OpenAI)
│   │   │   ├── database/      # Session manager
│   │   │   ├── schema/        # Schema introspection & retrieval
│   │   │   ├── sql/           # SQL generator & safety validator
│   │   │   └── pipeline.py    # Complete NL → Intent → SQL pipeline
│   │   └── main.py            # FastAPI entry point
│   └── tests/                 # Pytest test suite
├── frontend/
│   ├── src/
│   │   ├── components/        # React UI components (Navbar, Sidebar, Chat, Tables, SQL)
│   │   ├── services/          # API client services
│   │   ├── types/             # TypeScript type definitions
│   │   └── App.tsx            # Main application layout
│   └── vite.config.ts
├── sample_database/           # Sample e-commerce database & generation scripts
├── docker-compose.yml
├── README.md
└── .env.example
```
