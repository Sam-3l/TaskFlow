#!/bin/bash
set -e

# Run database migrations
flask db upgrade

# Start Gunicorn
exec gunicorn --bind 0.0.0.0:5000 manage:app