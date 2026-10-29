FROM public.ecr.aws/docker/library/python:3.12.15-alpine3.24
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 E2E_GATEWAY_ONLY=disposable-e2e
WORKDIR /gateway
COPY gateway.py ./gateway.py
USER 65534:65534
CMD ["python", "gateway.py"]
