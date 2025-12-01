#!/bin/bash

echo "=================================="
echo "Aave v3 Position Fetcher - Quick Start"
echo "=================================="
echo ""

# Check if Python is installed
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "Error: PostgreSQL is not installed. Please install PostgreSQL first."
    exit 1
fi

echo "Step 1: Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "Virtual environment created"
fi

source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo "Error: Failed to install dependencies"
    exit 1
fi

echo ""
echo "Step 2: Setting up environment variables..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo ".env file created. Please edit it with your PostgreSQL credentials."
    echo ""
    read -p "Press Enter after you've updated .env with your database credentials..."
else
    echo ".env file already exists"
fi

echo ""
echo "Step 3: Setting up database..."
source venv/bin/activate
python3 setup_database.py

if [ $? -ne 0 ]; then
    echo "Error: Failed to set up database. Please check your PostgreSQL credentials in .env"
    exit 1
fi

echo ""
echo "=================================="
echo "Setup complete! Next steps:"
echo "=================================="
echo ""
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Fetch Aave positions:"
echo "   python3 fetch_aave_positions.py"
echo ""
echo "3. Analyze the data:"
echo "   python3 query_positions.py"
echo ""
echo "See README.md for more details."
