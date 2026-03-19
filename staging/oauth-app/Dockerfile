FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN python manage.py collectstatic --noinput 2>/dev/null || true

EXPOSE 8001

CMD ["gunicorn", "oauth_staging.wsgi:application", "--bind", "0.0.0.0:8001"]
