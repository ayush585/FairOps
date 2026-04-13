FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities
COPY ../shared/ /app/shared/

# Copy SDK schemas
COPY ../../sdk/fairops_sdk/ /app/fairops_sdk/

# Copy auditor code
COPY . .

EXPOSE 8001

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
