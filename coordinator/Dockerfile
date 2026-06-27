FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy coordinator files into a package directory
COPY . ./coordinator/

# Create __init__.py if not present
RUN touch coordinator/__init__.py

EXPOSE 8000
CMD ["uvicorn", "coordinator.main:app", "--host", "0.0.0.0", "--port", "8000"]