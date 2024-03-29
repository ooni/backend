#!/bin/bash
DOCS_ROOT=dist/docs/
REPO_NAME="ooni/backend"
COMMIT_HASH=$(git rev-parse --short HEAD)

mkdir -p $DOCS_ROOT

strip_title() {
    # Since the title is already present in the frontmatter, we need to remove
    # it to avoid duplicate titles
    local infile="$1"
    cat $infile | awk 'BEGIN{p=1} /^#/{if(p){p=0; next}} {print}'
}

cat <<EOF>$DOCS_ROOT/00-index.md
---
# Do not edit! This file is automatically generated
# version: $REPO_NAME:$COMMIT_HASH
title: OONI Backend
description: OONI Backend documentation
slug: backend
---
EOF
strip_title README.md >> $DOCS_ROOT/00-index.md

cat <<EOF>$DOCS_ROOT/01-ooniapi.md
---
# Do not edit! This file is automatically generated
# version: $REPO_NAME:$COMMIT_HASH
title: OONI API
description: OONI API documentation
slug: backend/ooniapi
---
EOF
strip_title ooniapi/README.md >> $DOCS_ROOT/01-ooniapi.md

cat <<EOF>$DOCS_ROOT/02-ooniapi-services.md
---
# Do not edit! This file is automatically generated
# version: $REPO_NAME:$COMMIT_HASH
title: OONI API Services
description: OONI API Services documentation
slug: backend/ooniapi/services
---
EOF
strip_title ooniapi/services/README.md >> $DOCS_ROOT/02-ooniapi-services.md

