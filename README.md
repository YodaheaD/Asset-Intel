# AssetIntel Backend API

A FastAPI-based backend service for the AssetIntel application.

## Project Structure

```
assetintel-backend/
│
├── app/
│   ├── main.py              # FastAPI application entry point
│   ├── api/
│   │   └── v1/
│   │       └── health.py    # Health check endpoints
│   ├── models/
│   │   └── common.py        # Common Pydantic models
│   └── core/
│       └── config.py        # Application configuration
│
├── requirements.txt         # Python dependencies
└── README.md               # Project documentation
```

## Installation

1. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Running the Application

### Development Mode

```bash
# From the project root directory
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Or run directly with Python:
```bash
python app/main.py
```

### Access the API

- **API Documentation (Swagger UI):** http://localhost:8000/docs
- **Alternative Documentation (ReDoc):** http://localhost:8000/redoc
- **Health Check:** http://localhost:8000/api/v1/health
- **API Base URL:** http://localhost:8000/api/v1

## API Endpoints

### Health Check
- `GET /api/v1/health` - Basic health check
- `GET /api/v1/health/ready` - Readiness check for deployments

### Root
- `GET /` - Welcome message and API information

## Configuration

The application uses environment-based configuration. Create a `.env` file in the project root to override default settings:

```env
APP_NAME=AssetIntel Backend API
DEBUG=True
SECRET_KEY=your-secret-key-here
ENVIRONMENT=development
```

## Development

### Code Formatting
```bash
black app/
```

### Linting
```bash
flake8 app/
```

### Type Checking
```bash
mypy app/
```

### Testing
```bash
pytest
```

## Features

- ✅ FastAPI framework with automatic OpenAPI documentation
- ✅ Pydantic models for request/response validation
- ✅ Environment-based configuration
- ✅ CORS middleware for cross-origin requests
- ✅ Health check endpoints
- ✅ Structured project layout
- ✅ Development dependencies included

## Next Steps

1. Add database integration (SQLAlchemy, MongoDB, etc.)
2. Implement authentication and authorization
3. Add business logic endpoints
4. Set up logging and monitoring
5. Configure deployment settings
6. Add comprehensive tests

## License

[Add your license here]