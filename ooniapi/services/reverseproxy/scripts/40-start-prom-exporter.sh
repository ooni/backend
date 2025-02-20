#!/bin/bash

# This script is used to start the prometheus exporter for nginx.
# More about the exporter here: 
# https://github.com/nginx/nginx-prometheus-exporter

nginx-prometheus-exporter --nginx.scrape-uri=http://localhost:8080/stub_status &