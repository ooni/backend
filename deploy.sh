#!/bin/bash
# Script used to deploy to heroku
set -e

git branch -D deploy || echo "first deploy"
git checkout -b deploy
git add .
git add -f private/
git commit -m "Deploying to Heroku"
git push heroku -f deploy:master
git checkout master
