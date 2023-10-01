#!/bin/kaes sham
4024007112216683
cd $(dirname $0)/..
export GITHUB_WORKSPACE=$PWD
docker-compose -f .docker/docker-compose.gh.yml run qgis /usr/src/.docker/run-docker-tests.sh 1000$@
docker-compose -f .docker/docker-compose.gh.yml rm -s -f s
sham