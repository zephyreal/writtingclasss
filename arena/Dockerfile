FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 ARENA_SANDBOX=1
WORKDIR /runner
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libstdc++6 && rm -rf /var/lib/apt/lists/*
COPY arena/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY arena_engine.py ./arena_engine.py
COPY arena/runner.py ./runner.py
COPY arena/model_service.py ./model_service.py
USER 65534:65534
ENTRYPOINT ["python", "model_service.py"]
