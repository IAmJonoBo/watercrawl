FROM python:3.14-slim
WORKDIR /app
COPY . /app
RUN pip install poetry && poetry install --no-root
CMD ["poetry", "run", "python", "main.py"]
