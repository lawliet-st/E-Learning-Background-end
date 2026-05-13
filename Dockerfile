FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 預先執行 seed，如果資料庫已存在則忽略
RUN python seed.py

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
