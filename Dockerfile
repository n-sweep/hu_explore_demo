FROM python:3.13-bookworm

WORKDIR /app

COPY pyproject.toml ./
RUN pip install uv && uv venv .venv && uv pip install . --python /app/.venv/bin/python

COPY . .

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8501

# CMD ["streamlit", "run", "hu_explore_demo/main.py"]
