import zlib
import tempfile
from urlparse import urlparse


class S3Downloader(object):
    def __init__(self, access_key_id, secret_access_key, bucket_name=None):
        from boto.s3.connection import S3Connection
        self.s3_connection = S3Connection(access_key_id, secret_access_key)
        self.buckets = {
            bucket_name: self.s3_connection.get_bucket(bucket_name)
        }

    def uncompress_to_disk(self, key, fp):
        CHUNK_SIZE = 2048
        decompressor = zlib.decompressobj(16+zlib.MAX_WBITS)
        while True:
            chunk = key.read(CHUNK_SIZE)
            if not chunk:
                break
            fp.write(decompressor.decompress(chunk))
        fp.flush()
        fp.seek(0)

    def download(self, uri, fp=None):
        p = urlparse(uri)
        bucket_name = p.netloc
        if not self.buckets.get(bucket_name):
            self.buckets[bucket_name] = self.s3_connection.get_bucket(
                bucket_name)
        key = self.buckets[bucket_name].get_key(p.path)
        key.open('r')

        if fp is None:
            fp = tempfile.NamedTemporaryFile('wb+',
                                             prefix='s3-downloader-tmp',
                                             delete=False)
        if p.path.endswith('.gz'):
            self.uncompress_to_disk(key, fp)
        else:
            self.get_contents_to_file(fp)
        key.close()
        return fp
