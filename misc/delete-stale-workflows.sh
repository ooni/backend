#!/bin/bash
# Due to https://github.com/orgs/community/discussions/26256 if you rename a
# workflow you end up with a bunch of stale workflow names in the actions tab.
# 
# As a workaround you can delete the old runs so that they disappear from the
# UI:
# https://github.com/orgs/community/discussions/26256#discussioncomment-8224816

# To run it do:
# ./delete-stale-workflows.sh [WORKFLOW_NAME]
#
# eg.
# ./delete-stale-workflows.sh old_workflow_name.yml

WORKFLOW_NAME=$1

# To run this you will have to change the filter in:

gh run list --limit 500 --workflow=$WORKFLOW_NAME

read -p "Are you sure you want to delete the above (y/N)? " -n 1 -r
echo    # (optional) move to a new line
if [[ $REPLY =~ ^[Yy]$ ]]
then
    gh run list --limit 500 --workflow=$WORKFLOW_NAME --json databaseId | jq '.[].databaseId' | xargs -I{} gh run delete {}

fi
