#!/bin/bash
# OSINT Platform - Development Mode Startup Script

set -e

echo "🔧 Starting OSINT Platform in development mode..."

# Check prerequisites
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed"
    exit 1
fi

if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed"
    exit 1
fi

cd "$(dirname "$0")/.."

# Start infrastructure services (PostgreSQL, Redis)
echo ""
echo "🚀 Starting infrastructure services..."
docker-compose up -d postgres redis

echo "⏳ Waiting for services to be ready..."
sleep 5

# Setup backend
echo ""
echo "🐍 Setting up Python backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -e ".[dev]" 2>/dev/null || pip install -e ".[dev]" --break-system-packages

# Run migrations
echo ""
echo "🗄️  Running database migrations..."
alembic upgrade head

# Start backend API in background
echo ""
echo "🚀 Starting FastAPI server on http://localhost:8000"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000 &
API_PID=$!

# Start Celery worker in background
echo ""
echo "👷 Starting Celery worker..."
celery -A app.workers.tasks worker --loglevel=info --concurrency=2 &
WORKER_PID=$!

# Start frontend
echo ""
echo "🎨 Starting Next.js frontend on http://localhost:3000"
cd ../frontend
npm install
npm run dev &
FRONTEND_PID=$!

echo ""
echo "✅ All services started!"
echo ""
echo "📊 Services:"
echo "   Frontend:     http://localhost:3000"
echo "   Backend API:  http://localhost:8000"
echo "   API Docs:     http://localhost:8000/docs"
echo ""
echo "🛑 Press Ctrl+C to stop all services"

# Wait for interrupt
trap 'kill $API_PID $WORKER_PID $FRONTEND_PID 2>/dev/null; docker-compose down; exit' INT
wait
