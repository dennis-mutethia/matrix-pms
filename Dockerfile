# Use python base image
FROM python:3.13-slim-bullseye

# Install essentials
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
    
COPY requirements.txt .
#update pip & install dependencies
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

#To run in terminal
#uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4 --reload
