#!/bin/bash
# Entrypoint for Dataflow Flex Template
set -e

# Execute the pipeline
exec python -m src.streaming.pipeline "$@"
