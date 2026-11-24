FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/output
VOLUME ["/app/output"]

ENTRYPOINT ["python", "src/bz-anim.py"]
CMD ["--output", "/app/output/bz_reaction.gif"]
