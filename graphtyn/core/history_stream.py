"""Bounded JSONL capture with durable batch acknowledgements.

Explicit project/session selection is required. Native IDs survive rotation;
without them a changed prefix is rejected for review instead of guessing identity.
"""
from __future__ import annotations
import hashlib
import json
from datetime import datetime
from pathlib import Path
import time

from .history_import import _walk_records, _role, _content, _workspace
from .memory_topics import encoded_tokens


def ingest_jsonl(store, source, *, provider, external_session_id, agent_id,
                 consent, explicit_project_selection=False, batch_messages=30,
                 batch_tokens=12000, max_record_bytes=8 * 1024 * 1024, progress=None):
    if not consent: raise PermissionError('la captura requiere consentimiento')
    path = Path(source).expanduser().resolve()
    key = hashlib.sha256(f'{provider}\0{external_session_id}\0{path}'.encode()).hexdigest()
    with path.open('rb') as stream:
        prefix = hashlib.sha256(stream.read(min(4096, path.stat().st_size))).hexdigest()
    with store._connect() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS history_stream_progress(
            source_key TEXT PRIMARY KEY, path TEXT NOT NULL, prefix TEXT NOT NULL,
            offset INTEGER NOT NULL, record_index INTEGER NOT NULL, discovered INTEGER NOT NULL,
            processed INTEGER NOT NULL, excluded INTEGER NOT NULL, errors INTEGER NOT NULL,
            session_id TEXT, updated_at REAL NOT NULL)''')
        row = db.execute('SELECT * FROM history_stream_progress WHERE source_key=?', (key,)).fetchone()
    state = dict(row) if row else dict(offset=0, record_index=0, discovered=0, processed=0, excluded=0, errors=0, session_id=None)
    # Prefix comparison is only meaningful after 4096 bytes have been acknowledged.
    if row and (path.stat().st_size < state['offset'] or (state['offset'] >= 4096 and prefix != row['prefix'])):
        # Reconcile a rotated file by native identity, never by identical text.
        # If identities are missing, leave the old acknowledgement untouched.
        with path.open('rb') as verify:
            while True:
                line = verify.readline(max_record_bytes + 1)
                if not line: break
                if len(line) > max_record_bytes: raise ValueError('rotación con registro demasiado grande; revisión requerida')
                try: value = json.loads(line)
                except ValueError: continue
                for record in _walk_records(value):
                    if _role(record) and _content(record) and not any(record.get(k) is not None for k in ('id','uuid','message_id','step_index')):
                        raise ValueError('rotación sin IDs nativos: revisión requerida; no se avanzó el cursor')
        state = dict(offset=0, record_index=0, discovered=0, processed=0, excluded=0, errors=0, session_id=state['session_id'])
    if not explicit_project_selection:
        raise ValueError('la importación incremental requiere selección explícita del proyecto y sesión')
    session = store.ensure_external_session(agent_id, external_session_id, f'Conversación {external_session_id}', consent=True, reopen_closed=True)
    initial_processed = state["processed"]
    batch, cost = [], 0
    def commit(offset, record_index):
        nonlocal batch, cost
        if batch:
            store.ingest_turn(agent_id, external_session_id, session['task'], batch, consent=True, compact=True, provider='deterministic')
            state['processed'] += len(batch)
        with store._connect() as db:
            db.execute('INSERT INTO history_stream_progress VALUES(?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET prefix=excluded.prefix,offset=excluded.offset,record_index=excluded.record_index,discovered=excluded.discovered,processed=excluded.processed,excluded=excluded.excluded,errors=excluded.errors,session_id=excluded.session_id,updated_at=excluded.updated_at',
                (key, str(path), prefix, offset, record_index, state['discovered'], state['processed'], state['excluded'], state['errors'], session['id'], time.time()))
        state.update(offset=offset, record_index=record_index, session_id=session['id'])
        batch, cost = [], 0
        if progress and progress(dict(state)) is False: raise InterruptedError('captura interrumpida; lote confirmado')
    with path.open('rb') as stream:
        stream.seek(state['offset'])
        index = state['record_index']
        while True:
            start = stream.tell()
            line = stream.readline(max_record_bytes + 1)
            if not line: break
            if not line.endswith(b'\n') and len(line) <= max_record_bytes:
                # A writer may still be appending this record. Never acknowledge it.
                break
            index += 1
            state['discovered'] += 1
            if len(line) > max_record_bytes:
                while line and not line.endswith(b'\n'): line = stream.readline(max_record_bytes + 1)
                state['excluded'] += 1
                if not line: break
                commit(stream.tell(), index)
                continue
            try: root = json.loads(line)
            except (ValueError, UnicodeDecodeError):
                state['errors'] += 1
                commit(stream.tell(), index)
                continue
            if provider == 'codex' and isinstance(root, dict) and root.get('type') in {'event_msg', 'world_state', 'turn_context', 'compacted'}:
                state['excluded'] += 1
                if index % batch_messages == 0: commit(stream.tell(), index)
                continue
            root_sid = root.get('sessionId') or root.get('session_id') or root.get('conversation_id') if isinstance(root, dict) else None
            if root_sid and str(root_sid) != external_session_id:
                state['excluded'] += 1
                commit(stream.tell(), index)
                continue
            accepted = 0
            for child_index, record in enumerate(_walk_records(root)):
                role, content = _role(record), _content(record)
                if role not in {'user', 'assistant', 'tool'} or not content: continue
                sid = record.get('sessionId') or record.get('session_id') or record.get('conversation_id')
                if sid and str(sid) != external_session_id: continue
                mid = str(record.get('id') or record.get('uuid') or record.get('message_id') or (str(record['step_index']) if 'step_index' in record else None) or f'{external_session_id}:{index - 1}:{child_index}')
                metadata = {'source_message_id': mid, 'provider': provider, 'historical_source': str(path), 'source_sequence': [index - 1, child_index], 'capture_mode': 'historical_import'}
                stamp = record.get('timestamp') or record.get('created_at') or record.get('createdAt')
                if isinstance(stamp, str):
                    try: stamp = datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp()
                    except ValueError: stamp = None
                if isinstance(stamp, (int, float)): metadata['occurred_at'] = stamp / (1000 if stamp > 1e11 else 1)
                message = {'role': role, 'content': content, 'metadata': metadata}
                batch.append(message); cost += encoded_tokens(message); accepted += 1
            if not accepted: state['excluded'] += 1
            # The input record is atomic; do not checkpoint in the middle of it.
            if len(batch) >= batch_messages or cost >= batch_tokens or index % batch_messages == 0:
                commit(stream.tell(), index)
        if batch or stream.tell() == path.stat().st_size:
            # Do not consume an unterminated final line.
            commit(start if line and not line.endswith(b'\n') else stream.tell(), index - (1 if line and not line.endswith(b'\n') and len(line) > max_record_bytes else 0))
    return {'ok': True, **state, 'processed_this_run': state['processed'] - initial_processed, 'source': str(path), 'extraction': 'deterministic-limited',
            'pending_bytes': max(0, path.stat().st_size - state['offset']), 'counter_unit': 'records except processed (messages)'}


def watch_jsonl(store, source, *, interval=10, **kwargs):
    """Run capture continuously. A command suggestion never creates this lease."""
    import os
    key = hashlib.sha256(str(Path(source).resolve()).encode()).hexdigest()
    with store._connect() as db:
        db.execute('CREATE TABLE IF NOT EXISTS history_watchers(source_key TEXT PRIMARY KEY,pid INTEGER,heartbeat REAL,status TEXT,error TEXT)')
    def heartbeat(status, error=''):
        with store._connect() as db:
            db.execute('INSERT OR REPLACE INTO history_watchers VALUES(?,?,?,?,?)', (key, os.getpid(), time.time(), status, error))
    try:
        while True:
            heartbeat('processing')
            try:
                ingest_jsonl(store, source, **kwargs, progress=lambda stats: heartbeat('processing'))
                heartbeat('watching')
            except (ValueError, OSError) as exc:
                heartbeat('error', str(exc))
                raise
            time.sleep(max(1, min(30, interval)))
    finally:
        heartbeat('stopped')


def preview_jsonl(path, provider, max_record_bytes=8 * 1024 * 1024):
    """Discover session metadata without serializing transcripts into API jobs."""
    path=Path(path)
    groups={}; file_session=None; workspace=None
    if provider == 'antigravity':
        import re
        file_session=next((part for part in path.parts if re.fullmatch(r'[0-9a-f]{8}-[0-9a-f-]{27,}',part,re.I)),None)
    excluded=errors=records=0
    with path.open('rb') as stream:
        while True:
            line=stream.readline(max_record_bytes+1)
            if not line: break
            records+=1
            if len(line)>max_record_bytes:
                while line and not line.endswith(b'\n'): line=stream.readline(max_record_bytes+1)
                excluded+=1;continue
            try: root=json.loads(line)
            except ValueError: errors+=1;continue
            if not isinstance(root,dict): excluded+=1;continue
            if root.get('type')=='session_meta':
                payload=root.get('payload') or {}
                file_session=payload.get('id') or file_session
                workspace=_workspace(payload) or workspace
            file_session=root.get('sessionId') or root.get('session_id') or root.get('conversation_id') or file_session
            workspace=_workspace(root) or workspace
            if provider=='codex' and root.get('type') in {'event_msg','world_state','turn_context','compacted'}:
                excluded+=1;continue
            accepted=0
            for record in _walk_records(root):
                role,content=_role(record),_content(record)
                if role not in {'user','assistant','tool'} or not content: continue
                sid=str(record.get('sessionId') or record.get('session_id') or record.get('conversation_id') or file_session or path.stem)
                group=groups.setdefault(sid,{'message_count':0,'task':'Historical session','workspace':workspace,'occurred_at':None})
                if role=='user' and group['task']=='Historical session':
                    group['task']=content[:180]
                group['workspace']=group['workspace'] or _workspace(record) or workspace
                stamp=record.get('created_at') or record.get('timestamp') or record.get('createdAt')
                if isinstance(stamp,str):
                    try: stamp=datetime.fromisoformat(stamp.replace('Z','+00:00')).timestamp()
                    except ValueError: stamp=None
                if isinstance(stamp,(int,float)):
                    stamp=stamp/(1000 if stamp>1e11 else 1)
                    group['occurred_at']=min(group['occurred_at'] or stamp,stamp)
                group['message_count']+=1; accepted+=1
            if not accepted: excluded+=1
    agent='agy' if provider=='antigravity' else provider
    if provider=='openclaw' and path.parent.name=='sessions': agent=f'openclaw/{path.parent.parent.name}'
    from .shared_memory import SharedMemoryStore
    sessions=[]
    for sid,group in groups.items():
        group['task']=SharedMemoryStore._sanitize(group['task'],180)[0]
        fingerprint=hashlib.sha256(f'{provider}:{sid}:{path.stat().st_size}:{path.stat().st_mtime_ns}'.encode()).hexdigest()
        sessions.append({**group,'provider':provider,'agent_id':agent,'external_session_id':sid,'source':str(path),
                         'streaming_source':True,'messages':[],'fingerprint':fingerprint})
    return {'sessions':sessions,'records':records,'excluded':excluded,'errors':errors}
