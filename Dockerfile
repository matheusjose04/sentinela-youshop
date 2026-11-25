# Imagem do Sentinela (interface Streamlit). O deploy oficial continua no Streamlit Community Cloud.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

# Dependências primeiro, para aproveitar o cache de camadas.
COPY requirements.txt .
RUN pip install -r requirements.txt

# Usuário sem privilégios de root.
RUN useradd --create-home --uid 10001 sentinela

COPY --chown=sentinela:sentinela . .

USER sentinela

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0"]
