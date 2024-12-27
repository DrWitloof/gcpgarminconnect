# Gebruik een lichte Python-image
FROM python:3.12-slim

# Installeer afhankelijkheden
WORKDIR /app
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Voeg de Flask-app toe
COPY . .

# Start de applicatie
CMD ["python", "app.py"]
