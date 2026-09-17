#!/bin/bash
# OSINT Platform - Quick Setup Script

set -e  # Exit on error

echo "🚀 Setting up OSINT Platform..."

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "✅ Docker and Docker Compose found"

# Navigate to project root
cd "$(dirname "$0")/.."

# Setup backend environment
echo ""
echo "📝 Setting up backend environment..."
if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo "⚠️  Created backend/.env from template. Please edit it with your credentials:"
    echo "   - DEEPSEEK_API_KEY"
    echo "   - TG_API_ID"
    echo "   - TG_API_HASH"
    echo ""
    read -p "Press Enter after you've edited the .env file..."
else
    echo "✅ backend/.env already exists"
fi

# Build and start services
echo ""
echo "🏗️  Building Docker images..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

# Wait for services to be ready
echo ""
echo "⏳ Waiting for PostgreSQL to be ready..."
sleep 5

# Run database migrations
echo ""
echo "🗄️  Running database migrations..."
docker-compose exec -T api alembic upgrade head

echo ""
echo "✅ Setup complete!"
echo ""
echo "📊 Service URLs:"
echo "   Frontend:     http://localhost:3000"
echo "   Backend API:  http://localhost:8000"
echo "   API Docs:     http://localhost:8000/docs"
echo ""
echo "📋 Useful commands:"
echo "   View logs:         docker-compose logs -f"
echo "   Stop services:     docker-compose down"
echo "   Restart services:  docker-compose restart"
echo ""
echo "⚠️  Don't forget to create a task and start it from the web interface!"
