import os
import zlib
import math
import tempfile
from urlparse import urlparse

from filechunkio import FileChunkIO


class S3CachedConnector(object):
    def __init__(self, access_key_id, secret_access_key, bucket_name=None):
        from boto.s3.connection import S3Connection
        self.s3_connection = S3Connection(access_key_id, secret_access_key)
        self.buckets = {
            bucket_name: self.s3_connection.get_bucket(bucket_name)
        }

    def get_bucket(self, bucket_name):
        if not self.buckets.get(bucket_name):
            self.buckets[bucket_name] = self.s3_connection.get_bucket(
                bucket_name)
        return self.buckets[bucket_name]


class S3Downloader(S3CachedConnector):
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
        key = self.get_bucket(bucket_name).get_key(p.path)
        key.open('r')

        if fp is None:
            fp = tempfile.NamedTemporaryFile('wb+',
                                             prefix='s3-downloader-tmp',
                                             delete=False)
        if p.path.endswith('.gz'):
            self.uncompress_to_disk(key, fp)
        else:
            key.get_contents_to_file(fp)
            fp.seek(0)
        key.close()
        return fp


class S3Uploader(S3CachedConnector):
    # 50 MiB
    chunk_size = 52428800

    def upload(self, bucket_name, source_path, dst_path=None):
        if dst_path is None:
            dst_path = os.path.basename(source_path)

        source_size = os.stat(source_path).st_size
        bucket = self.get_bucket(bucket_name)
        mp = bucket.initiate_multipart_upload(dst_path)

        chunk_count = int(math.ceil(source_size / float(self.chunk_size)))

        for i in range(chunk_count):
            offset = self.chunk_size * i
            bytes = min(self.chunk_size, source_size - offset)
            with FileChunkIO(source_path, 'r', offset=offset,
                             bytes=bytes) as fp:
                mp.upload_part_from_file(fp, part_num=i + 1)
        mp.complete_upload()
