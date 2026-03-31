FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install CLI dependencies if required (e.g. for gcal-cli or mutt, though we will likely use python subprocess with specific simple python CLI scripts to avoid system deps overhead unless needed)
# RUN apt-get update && apt-get install -y ...

COPY . .
ENV PYTHONPATH=/app

CMD ["python", "-m", "src.main"]
