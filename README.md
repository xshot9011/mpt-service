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

---

## Running Tests

Django uses its built-in test framework along with the `manage.py test` command to discover and run tests.

### How it works:
1. **Test Discovery**: Django finds all files named `tests.py` or starting with `test_` inside your apps, and runs all methods starting with `test_` within `TestCase` classes.
2. **Test Database**: It creates a brand new, empty database just for testing, applies all migrations, and destroys it when the tests finish. This ensures tests are isolated and don't affect your real data.
3. **Isolation**: Every test runs inside a database transaction that is rolled back at the end of the test. Any data created in a test (or its `setUp` method) is erased before the next test runs.

### Command Examples:

**Run all tests in the project:**
```bash
python3 manage.py test
```

**Run all tests for a specific app (e.g., `portfolio`):**
```bash
python3 manage.py test portfolio
```

**Run tests in a specific class:**
```bash
python3 manage.py test portfolio.tests.SymbolNavTests
```

**Run a single specific test:**
```bash
python3 manage.py test portfolio.tests.SymbolNavTests.test_nav_fixed_returns_fixed_value
```

### Running Tests in Docker
If you are developing using Docker (e.g., Option 1), you should run the test command inside the running container. 

Assuming your app service is named `web` (default in the `docker-compose.dev.yml`), run:
```bash
docker-compose -f docker-compose.dev.yml exec web python3 manage.py test
```
