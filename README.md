# MPT Service

This project can be run locally in three different ways depending on your development needs.

## Option 1: Docker Compose Development Environment (Recommended)

This is the recommended approach for development because running the Django development server locally provides **automatic hot-reloading** when you make code changes, while keeping everything contained within Docker.

This option maps your local directory into the container, so any changes made to your code on your host machine will immediately reflect in the running container.

**Step 1:** Start the application using the development docker-compose file.
```bash
docker-compose -f docker-compose.dev.yml up --build
```
The application will be accessible at `http://127.0.0.1:8000/`.

---

## Option 2: Local Development (PostgreSQL in Docker + Django Locally)

This is an alternative development approach where the database is containerized but the Django process runs natively on your machine.

**Step 1:** Start the PostgreSQL database container in the background.
```bash
docker-compose -f docker-compose.db.yml up -d
```

**Step 2:** Start the Django development server locally.
Make sure your virtual environment is activated and dependencies are installed (`pip install -r requirements.txt`), then run:
```bash
python3 manage.py runserver
```
The application will be accessible at `http://127.0.0.1:8000/`.

---

## Option 3: Full Production-like Environment (All Services)

This approach runs the entire stack—both the Django application and the PostgreSQL database—inside Docker containers exactly as they would in production.

> **Note:** The Django application is served using **Gunicorn** in the `docker-compose.yml` setup. It acts as a production-like server and **will not automatically reload** when you modify the code. If you change your code, you will need to rebuild or restart the container.

To spin up the full environment, run:
```bash
docker-compose up --build
```
The application will be accessible at `http://127.0.0.1:8000/`.
