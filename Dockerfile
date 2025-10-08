# file: Dockerfile
# Why: Ensures container boots successfully even if you haven't wired the real flows yet.
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
CMD ["python", "-m", "app.cli", "idle"]
