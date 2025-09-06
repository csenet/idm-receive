FROM python:3.11-slim

WORKDIR /app

# 必要なライブラリをインストール（フォントサポート含む）
RUN apt-get update && apt-get install -y \
    fonts-dejavu-core \
    fonts-noto-cjk \
    fontconfig \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server.py .

RUN mkdir -p fortune_images

EXPOSE 8000

CMD ["python", "server.py"]