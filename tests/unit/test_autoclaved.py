import hashlib
from measurements.pages import decompress_autoclaved

# The s3 URL is something like:
# https://s3.amazonaws.com/ooni-public/sanitised/2017-07-08/20170707T051609Z-IR-AS44244-web_connectivity-20170707T051545Z_AS44244_ujwFYcBJXcL2MjZnHXhBqVEOG2iHR0AuPUHB7aGGqUhdtvz70h-0.2.0-probe.json

AUTOCLAVED = {
    'many_frames': {
        'autoclaved_filename': '2017-07-08/20170707T051609Z-IR-AS44244-web_connectivity-20170707T051545Z_AS44244_ujwFYcBJXcL2MjZnHXhBqVEOG2iHR0AuPUHB7aGGqUhdtvz70h-0.2.0-probe.json.lz4',
        'textname': '2017-07-08/20170707T051609Z-IR-AS44244-web_connectivity-20170707T051545Z_AS44244_ujwFYcBJXcL2MjZnHXhBqVEOG2iHR0AuPUHB7aGGqUhdtvz70h-0.2.0-probe.json',
        'frame_off': 0,
        'total_frame_size': 15485694 + 1724,
        'intra_off': 0,
        'report_size': 74695236,
        # This doesn't actually match that which is in s3
        'expected_shasum': 'bfbf98eee1fbdec63b3421ece09db6553cfb27fb4ca2942bf4762255317bd7de'
    },
    'single_frame': {
        'autoclaved_filename': '2016-07-07/http_invalid_request_line.0.tar.lz4',
        'textname': '2016-07-07/20160706T015518Z-CH-AS200938-http_invalid_request_line-20160706T015558Z_AS200938_iVsUREhX4hTEoHTOfyTFXyLvXKGGd80sFE3Xw3pJIUg2TDXr9I-0.2.0-probe.json',
        'frame_off': 0,
        'total_frame_size': 1897,
        'intra_off': 1536,
        'report_size': 3118,
        # Note this doesn't match exactly what is in sanitised
        'expected_shasum': 'e13999959d636ad2b5fd8d50493a257a2c616b0adad086bf7211de5f09463f6d'
    }
}

def test_decompress(client):
    for name, ac in AUTOCLAVED.items():
        decompressor = decompress_autoclaved(
                ac['autoclaved_filename'],
                ac['frame_off'],
                ac['total_frame_size'],
                ac['intra_off'],
                ac['report_size'])
        download_size = 0
        h = hashlib.sha256()
        g = decompressor()
        all_data = b''
        for chunk in g:
            all_data += chunk
            h.update(chunk)
        assert len(all_data) == ac['report_size'], len(all_data)
        assert h.hexdigest() == ac['expected_shasum'], h.hexdigest()
