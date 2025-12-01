#!/bin/bash
# Helper script to activate the virtual environment
# Usage: source activate.sh

if [ -d "venv" ]; then
    source venv/bin/activate
    echo "Virtual environment activated!"
    echo "Python: $(which python3)"
    echo ""
    echo "To deactivate, run: deactivate"
else
    echo "Error: Virtual environment not found. Run ./quickstart.sh first."
fi
