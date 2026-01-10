FROM python:3.12-slim

WORKDIR /app

RUN pip install poetry

COPY pyproject.toml ./
RUN poetry config virtualenvs.create false && poetry install --no-root --no-interaction --no-ansi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
