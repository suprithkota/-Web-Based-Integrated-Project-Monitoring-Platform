import base64
import sys
from io import BytesIO
from urllib.parse import urlencode

def response(app, event, context):
    headers = event.get('headers') or {}
    multi_headers = event.get('multiValueHeaders') or {}

    query_params = event.get('queryStringParameters') or {}
    multi_query = event.get('multiValueQueryStringParameters') or {}

    if multi_query:
        query_string = urlencode(multi_query, doseq=True)
    elif query_params:
        query_string = urlencode(query_params)
    else:
        query_string = ''

    body = event.get('body') or ''
    if event.get('isBase64Encoded', False):
        body_bytes = base64.b64decode(body)
    else:
        body_bytes = body.encode('utf-8') if isinstance(body, str) else body

    path = event.get('path', '/')

    environ = {
        'REQUEST_METHOD': event.get('httpMethod', 'GET'),
        'SCRIPT_NAME': '',
        'PATH_INFO': path,
        'QUERY_STRING': query_string,
        'SERVER_NAME': headers.get('host', 'localhost'),
        'SERVER_PORT': headers.get('x-forwarded-port', '443'),
        'SERVER_PROTOCOL': 'HTTP/1.1',
        'wsgi.version': (1, 0),
        'wsgi.url_scheme': headers.get('x-forwarded-proto', 'https'),
        'wsgi.input': BytesIO(body_bytes),
        'wsgi.errors': sys.stderr,
        'wsgi.multithread': False,
        'wsgi.multiprocess': False,
        'wsgi.run_once': False,
        'CONTENT_LENGTH': str(len(body_bytes)),
        'CONTENT_TYPE': headers.get('content-type', headers.get('Content-Type', '')),
    }

    for key, value in headers.items():
        key = key.upper().replace('-', '_')
        if key not in ('CONTENT_TYPE', 'CONTENT_LENGTH'):
            environ[f'HTTP_{key}'] = value

    response_status = {}
    response_headers = []

    def start_response(status, res_headers, exc_info=None):
        response_status['status'] = status
        response_headers.extend(res_headers)

    app_iter = app(environ, start_response)
    try:
        response_body = b''.join(app_iter)
    finally:
        if hasattr(app_iter, 'close'):
            app_iter.close()

    status_code = int(response_status['status'].split()[0])

    headers_dict = {}
    multi_headers_dict = {}
    for k, v in response_headers:
        lk = k.lower()
        if lk == 'set-cookie':
            multi_headers_dict.setdefault(k, []).append(v)
        else:
            headers_dict[k] = v

    is_base64 = False
    content_type = headers_dict.get('Content-Type', headers_dict.get('content-type', ''))
    if any(binary_type in content_type for binary_type in ['image/', 'application/octet-stream', 'font/', 'application/pdf']):
        is_base64 = True
        body_out = base64.b64encode(response_body).decode('utf-8')
    else:
        try:
            body_out = response_body.decode('utf-8')
        except UnicodeDecodeError:
            is_base64 = True
            body_out = base64.b64encode(response_body).decode('utf-8')

    res = {
        'statusCode': status_code,
        'headers': headers_dict,
        'body': body_out,
        'isBase64Encoded': is_base64
    }
    if multi_headers_dict:
        res['multiValueHeaders'] = multi_headers_dict

    return res
