FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

ENV EZOP_PORT=13000

EXPOSE 13000

CMD ["sh", "-c", "python -m hypercorn app.main:app --bind 0.0.0.0:${EZOP_PORT}"]
