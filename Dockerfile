FROM python:3.9-slim

WORKDIR /code

COPY src/ .

# Přidej správná oprávnění ke všem souborům (včetně configuration.py)
RUN chmod -R a+r /code

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


CMD ["python", "main.py"]