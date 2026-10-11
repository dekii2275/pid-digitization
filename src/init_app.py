# Copyright (c) Microsoft Corporation.
# Licensed under the MIT license.
from prometheus_client import start_http_server
from prometheus_fastapi_instrumentator import Instrumentator

import app.utils.override_imwrite
import logger_config
from app.queue_consumer import start_consumer_worker
from app.routes.controller import app

"""
    Creates the app for the docker
"""
logger = logger_config.get_logger(__name__)
Instrumentator().instrument(app).expose(app, endpoint="")

start_http_server(port=7000)

start_consumer_worker()

if __name__ == "__main__":
    import uvicorn

    from app.config import config

    uvicorn.run(app, host="0.0.0.0", port=config.port)
