FROM pytorch/pytorch

# Disable MKLDNN (fix for "could not create a primitive")
ENV MKLDNN_VERBOSE=0
ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1

WORKDIR /app

COPY . .
RUN pip install uv && uv venv .venv && uv pip install . --python /app/.venv/bin/python


ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8501

CMD ["/bin/sh", "-c", ". /app/.venv/bin/activate && streamlit run hu_explore_demo/main.py"]


# docker stop exploredemo && docker rm exploredemo && docker rmi exploredemo:latest && \
# docker build -t exploredemo . && \
# docker run -dit --name exploredemo -e TS_IP="$(tailscale ip --4)" -v "${PWD}":/app -p 8501:8501 exploredemo && \
# docker exec -it exploredemo bash
