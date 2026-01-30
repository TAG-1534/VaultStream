FROM python:3.9-slim
WORKDIR /vaultstream
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 5000
# Updated to run the new filename
CMD ["python", "VaultStream.py"]