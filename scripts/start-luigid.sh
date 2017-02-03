#!/bin/sh
VENV_PATH="${HOME}/venv/bin"

${VENV_PATH}/python ${VENV_PATH}/luigid --address 127.0.0.1 \
                                        --port 8082 --pidfile luigid.pid \
                                        --logdir luigid.log \
                                        --state-path luigi-state.pickle \
                                        --background
