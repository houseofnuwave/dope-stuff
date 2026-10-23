# Optional local/container pilot. Not a production deployment template.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/form
RUN groupadd -r form && useradd --no-log-init -r -g form form && mkdir /data && chown form:form /data
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY tools/ops_backup.py ./tools/ops_backup.py
USER form
ENV FORM_DATA_DIR=/data FORM_ENV=development FORM_COOKIE_SECURE=false
EXPOSE 8000
CMD ["sh","-c","exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
