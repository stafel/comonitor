FROM python:3

EXPOSE 8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libudev-dev pkg-config \
    && rm -rf /var/lib/apt/lists/*

COPY app/requirements.txt requirements.txt

RUN HIDAPI_WITH_HIDRAW=1 pip install --no-binary=hidapi -r requirements.txt

COPY app/ .

#CMD [ "python", "./main.py" ]
CMD [ "fastapi", "run", "./main.py"]
