# Batelec Power Interruption API

A FastAPI-based API for managing power interruption data for Batelec.

## Features

- Complete CRUD operations for power interruptions and notices
- Import data from JSON file
- Search power interruptions by date
- Search notices by affected area
- Manage affected customers and specific activities
- RESTful API with Swagger documentation

## Setup

### Prerequisites

- Python 3.8+
- pip (Python package manager)

### Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd batelec
```

2. Create a virtual environment (optional but recommended):
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file in the root directory with the following variables:

```
DATABASE_URL=sqlite:///./batelec.db
```

You can change the database URL to use a different database if needed.

## Running the Application

### Quick Setup (Database + Server)

To set up the database and start the server in one step:

```bash
python setup_db.py
```

This will:
1. Start the FastAPI server
2. Import data from the JSON file
3. Keep the server running until you press Ctrl+C

### Manual Setup

To start the server manually:

```bash
python main.py
```

The server will run at http://localhost:8000

## API Documentation

Once the server is running, you can access the API documentation at:

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

### Power Interruptions

- `GET /api/data/power-interruptions` - Get all power interruptions
- `GET /api/data/power-interruptions/{interruption_id}` - Get a specific power interruption
- `POST /api/data/power-interruptions` - Create a new power interruption
- `PUT /api/data/power-interruptions/{interruption_id}` - Update a power interruption
- `DELETE /api/data/power-interruptions/{interruption_id}` - Delete a power interruption
- `GET /api/data/power-interruptions/by-date/{date}` - Get power interruptions by date

### Power Interruption Notices

- `GET /api/data/notices` - Get all notices
- `GET /api/data/notices/{notice_id}` - Get a specific notice
- `POST /api/data/notices` - Create a new notice
- `PUT /api/data/notices/{notice_id}` - Update a notice
- `DELETE /api/data/notices/{notice_id}` - Delete a notice
- `GET /api/data/notices/by-area/{area}` - Get notices by affected area

### Affected Customers

- `GET /api/data/customers` - Get all affected customers
- `GET /api/data/customers/{customer_id}` - Get a specific customer

### Specific Activities

- `GET /api/data/activities` - Get all specific activities
- `GET /api/data/activities/{activity_id}` - Get a specific activity

### Data Import

- `POST /api/data/import` - Import data from the JSON file

### Full Data

- `GET /api/data/full` - Get full power interruptions data in the same format as the JSON file

## Project Structure

```
batelec/
├── db/
│   └── db.py              # Database connection setup
├── models/
│   └── models.py          # Pydantic models for data validation
├── routers/
│   └── data.py            # API routes for power interruption data
├── schemas/
│   └── schemas.py         # SQLAlchemy ORM models
├── utils/
│   └── utils.py           # Utility functions for database operations
├── main.py                # FastAPI application entry point
├── setup_db.py            # Script to set up the database
└── README.md              # This file
```

## License

[MIT License](LICENSE)
