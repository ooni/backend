import os
import errno

from six.moves.urllib.parse import urlparse, urljoin

from sqlalchemy import exists

def get_download_url(app, bucket_date, filename):
    url = "https://s3.amazonaws.com/"
    # strip the leading s3://
    url += app.config['REPORTS_DIR'][5:]
    return urljoin(url, bucket_date, filename)
