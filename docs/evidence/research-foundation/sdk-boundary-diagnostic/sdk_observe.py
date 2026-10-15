import hashlib
import importlib.metadata as md
import json
import logging
import os
from pathlib import Path
import sys
import threading
import time

fd = int(sys.argv[1])
observed = []
boundaries = {}

def boundary(name, details=None):
    row = boundaries.setdefault(name, {'count': 0})
    row['count'] += 1
    if details is not None:
        row.update(details)

def safe_stacks():
    result = []
    for frame in sys._current_frames().values():
        rows = []
        while frame is not None and len(rows) < 10:
            filename = frame.f_code.co_filename
            if '/moomoo/' in filename or filename.endswith('/threading.py'):
                rows.append({'file': Path(filename).name, 'function': frame.f_code.co_name, 'line': frame.f_lineno})
            frame = frame.f_back
        result.append(rows)
    return result
def emit(value):
    os.write(fd,(json.dumps(value)+'\n').encode())
def profile(frame,event,arg):
    filename = frame.f_code.co_filename
    name = frame.f_code.co_name
    if '/moomoo/' in filename:
        if event == 'return' and name == 'pack_pb_req':
            boundary('pack_return', {'ret_code': arg[0] if isinstance(arg, tuple) and type(arg[0]) is int else None})
        if event == 'return' and name == 'do_send' and filename.endswith('/network_manager.py'):
            boundary('socket_send_return', {'bytes_sent': frame.f_locals.get('size', 0), 'ret_code': frame.f_locals.get('ret_code')})
        if event == 'call' and name == 'on_recv' and filename.endswith('/open_context_base.py'):
            boundary('context_received', {'byte_count': len(frame.f_locals.get('data', b''))})
        if event == 'call' and name == '_handle_init_connect_rsp':
            boundary('init_response_handler_called')
        if event == 'return' and name == '_send_init_connect_sync':
            boundary('init_query_return', {'ret_code': arg[0] if isinstance(arg, tuple) and type(arg[0]) is int else None})
    if event == 'call' and frame.f_code.co_name == 'pack_pb_req' and frame.f_code.co_filename.endswith('/moomoo/common/utils.py'):
        proto = frame.f_locals['proto_id']
        observed.append(proto)
        emit({'sdk_pack_protocol_id':proto,'original_sdk_pack_called':True})
        if proto != 1001:
            emit({'disallowed_auto_rpc':proto,'stopped_before_pack':True})
            os._exit(3)
sys.setprofile(profile)
threading.setprofile_all_threads(profile)
try:
    import moomoo
    from moomoo.common.ft_logger import logger
    logger.file_level = logging.CRITICAL+1
    logger.console_level = logging.CRITICAL+1
    from moomoo.common.open_context_base import ContextStatus
    emit({'sdk_imported':True,'sdk_version':moomoo.__version__,'pid':os.getpid()})
    started = time.monotonic()
    ctx = moomoo.OpenQuoteContext(host='127.0.0.1',port=11112,is_encrypt=False,is_async_connect=True)
    seen_status=[]
    while time.monotonic()-started<25:
        current=str(ctx.status)
        if not seen_status or current != seen_status[-1]:
            seen_status.append(current)
            emit({'sdk_status_transition':current,'seconds':round(time.monotonic()-started,3),'server_connection_id':ctx.get_sync_conn_id()})
        if ctx.status == ContextStatus.READY: break
        time.sleep(.01)
    emit({'diagnostic_boundaries': boundaries, 'sdk_thread_stacks': safe_stacks(), 'diagnostic_only': True})
    conn = ctx.get_sync_conn_id()
    status = ctx.status
    ready = status == ContextStatus.READY and type(conn) is int and conn > 0
    module = Path(moomoo.__file__)
    emit({'sdk_version':moomoo.__version__,'distribution_version':md.version('moomoo_api'),'module':str(module),'module_sha256':hashlib.sha256(module.read_bytes()).hexdigest(),'status':str(status),'status_transitions':seen_status,'server_connection_id':conn,'protocol_handshake':ready,'packed_protocol_ids':list(observed),'connect_seconds':round(time.monotonic()-started,3),'pid':os.getpid(),'namespaces':{n:os.readlink('/proc/self/ns/'+n) for n in ['user','net','mnt','pid']}})
    ctx.close()
    end = time.monotonic()+3
    while ctx.status != ContextStatus.CLOSED and time.monotonic()<end:
        time.sleep(.01)
    emit({'sdk_close_called':True,'sdk_status_after_close':str(ctx.status),'sdk_closed':ctx.status == ContextStatus.CLOSED,'packed_protocol_ids':list(observed)})
except BaseException as e:
    emit({'sdk_exception_class':type(e).__name__,'protocol_handshake':False})
    raise SystemExit(2)
