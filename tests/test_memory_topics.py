import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.core.memory_topics import encoded_tokens


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAPHTYN_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('GRAPHTYN_MEMORY_EMBEDDINGS', 'none')
    return SharedMemoryStore(tmp_path / 'project')


def populate(store, count=1101):
    session = store.start_session('codex', 'Texture and Android work', capture_enabled=True)
    for i in range(count):
        store.append_message(session['id'], 'user' if i % 2 == 0 else 'assistant',
            f'Texturas Android {i}', metadata={'source_message_id': str(i), 'occurred_at': 10})
    return session['id']


def test_all_messages_resume_and_concurrent_processing(store):
    sid = populate(store)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda _: store.process_topics(sid), range(2)))
    assert sum(r['processed'] for r in results) == 1101
    assert store.topic_coverage()['pending'] == 0
    assert store.process_topics(sid)['processed'] == 0
    with store._connect() as db:
        assert db.execute('SELECT COUNT(*) FROM topic_messages').fetchone()[0] == 1101
    assert store.topics('1100')['topics']


def test_window_order_edges_permissions_and_budget(store):
    sid = populate(store, 31)
    messages = store.list_messages(sid)
    window = store.message_window(messages[15]['id'])
    assert len(window['messages']) == 21
    assert [m['id'] for m in window['messages']] == [m['id'] for m in messages[5:26]]
    assert window['estimated_tokens'] <= 3000
    assert encoded_tokens(window) <= 3000
    assert len(store.message_window(messages[0]['id'])['messages']) == 11
    with store._connect() as db:
        db.execute('UPDATE sessions SET capture_enabled=0 WHERE id=?', (sid,))
    with pytest.raises(PermissionError): store.message_window(messages[0]['id'], requester_agent='agy')
    assert store.message_window(messages[0]['id'], requester_agent='codex')['ok']


def test_state_evidence_merge_and_split_audit(store):
    sid = populate(store, 4)
    store.process_topics(sid)
    rows = store.topics()['topics']
    a, b = rows[0]['id'], rows[1]['id']
    detail = store.topic(a)
    store.topic_update(a, requester_agent='codex', reason='Declaración del agente', state='resuelto', verification='declarado')
    assert store.topic(a)['topic']['verification'] == 'declarado'
    with pytest.raises(ValueError):
        store.topic_update(a, requester_agent='codex', reason='No evidence', verification='prueba superada')
    with pytest.raises(ValueError):
        store.topic_update(a, requester_agent='codex', reason='Wrong source', verification='confirmado por usuario', message_ids=['missing'])
    store.topic_update(a, requester_agent='codex', reason='Prueba falló', state='reabierto')
    store.topic_update(a, requester_agent='codex', reason='Continuación revisada', merge_into=b)
    assert len(store.topic(b)['episodes']) == 2
    result = store.topic_update(b, requester_agent='codex', reason='Separar peticiones', split_episode=detail['episodes'][0]['id'])
    assert store.topic(result['split_topic'])['events']


def test_repeated_text_with_distinct_source_ids_is_preserved(store):
    sid = store.start_session('codex', 'Buttons', capture_enabled=True)['id']
    first = store.append_message(sid, 'user', 'OK', metadata={'source_message_id': 'a'})
    second = store.append_message(sid, 'user', 'OK', metadata={'source_message_id': 'b'})
    repeat = store.append_message(sid, 'user', 'OK', metadata={'source_message_id': 'a', 'historical_source': 'rotated'})
    assert first['id'] != second['id']
    assert first['id'] == repeat['id']


def test_context_complete_response_budget(store):
    sid = populate(store, 40)
    store.process_topics(sid)
    result = store.context('Texturas', token_budget=1800, include_graph=False)
    assert encoded_tokens(result) <= 1800
    assert result['do_not_expand'] is False
    assert result['topics']


def test_backup_preserves_existing_memories(store, tmp_path):
    sid = store.start_session('agy', 'Existing')['id']
    mid = store.checkpoint(sid, 'fact', 'Existing fact', 'Preserve me')['id']
    result = store.backup(tmp_path / 'backup.db')
    restored = SharedMemoryStore(store.workspace, db_path=result['backup'])
    assert restored.get(mid)['content'] == 'Preserve me'


def test_topic_graph_connects_topics_sessions_and_agents(store):
    sid = populate(store, 8)
    store.process_topics(sid)
    graph = store.topic_graph(limit=100)
    kinds = {node['kind'] for node in graph['nodes']}
    assert graph['metadata']['topic_count'] >= 4
    assert {'memory_topic', 'memory_session', 'memory_agent'} <= kinds
    assert graph['links']
    assert graph['metadata']['coverage']['pending'] == 0
    labels = {link['label'] for link in graph['links']}
    assert 'continuación' not in labels
    assert all(node.get('reference', '').startswith('N-') for node in graph['nodes'])


def test_topic_graph_marks_possible_relations_ambiguous(store):
    sid = store.start_session('agy', 'Relations', capture_enabled=True)['id']
    for index, text in enumerate([
        'Android botones textura interfaz',
        'Android botones textura navegación',
        'Android botones textura pruebas',
    ]):
        store.append_message(sid, 'user', text)
    store.process_topics(sid)
    graph = store.topic_graph(limit=100)
    possible = store.relation_candidates(requester_agent='agy')['candidates']
    assert possible
    assert all(item['status'] == 'pending' for item in possible)
    assert not [link for link in graph['links'] if link['label'] == 'posible relación']


def test_node_references_and_relation_review_are_stable(store):
    sid = store.start_session('agy', 'Review one', capture_enabled=True)['id']
    sid2 = store.start_session('agy', 'Review two', capture_enabled=True)['id']
    store.append_message(sid, 'user', 'Android botones textura interfaz')
    store.append_message(sid2, 'user', 'Android botones textura navegación')
    store.process_topics(sid); store.process_topics(sid2)
    topics = store.topics(requester_agent='agy')['topics']
    assert topics[0]['reference'].startswith('N-')
    assert store.resolve_node_reference(topics[0]['reference'], requester_agent='agy')['topic']['id'] == topics[0]['id']
    candidate = store.relation_candidates(requester_agent='agy')['candidates'][0]
    reviewed = store.relation_review(candidate['id'], status='accepted', actor='agy', reason='Comparten la misma textura de navegación')
    assert reviewed['status'] == 'accepted'
    links = store.topic_graph(requester_agent='agy')['links']
    assert any(link['confidence'] == 'REVIEWED' for link in links)


def test_topics_keep_button_work_items_separate_and_continue_same_item(store):
    session = store.start_session('agy', 'Button work', capture_enabled=True)
    sid = session['id']
    for role, text in [
        ('user', 'Cambia el color del botón 2'),
        ('assistant', 'El botón 2 queda pendiente de verificación'),
        ('user', 'Cambia el color del botón 10'),
        ('assistant', 'El botón 10 queda pendiente de verificación'),
        ('user', 'Ahora usa azul para el botón 2'),
    ]:
        store.append_message(sid, role, text)
    store.process_topics(sid)
    with store._connect() as db:
        rows = db.execute('SELECT id,title FROM topics ORDER BY created_at').fetchall()
        entity_rows = db.execute('SELECT kind,entity_key FROM entities ORDER BY entity_key').fetchall()
        relation_rows = db.execute("SELECT relation FROM topic_relations WHERE relation='mismo elemento'").fetchall()
        episode_counts = db.execute('SELECT topic_id,COUNT(*) FROM topic_episodes GROUP BY topic_id').fetchall()
    assert len(rows) == 2
    assert {('button', '2'), ('button', '10')} <= {(row[0], row[1]) for row in entity_rows}
    assert relation_rows == []
    assert sorted(count for _, count in episode_counts) == [1, 2]


def test_distinct_button_topics_are_connected_by_explicit_entity(store):
    session = store.start_session('agy', 'Button relation', capture_enabled=True)
    sid = session['id']
    for text in ('Cambia el color del botón 2', 'Cambia el tamaño del botón 2'):
        store.append_message(sid, 'user', text)
    store.process_topics(sid)
    graph = store.topic_graph(limit=100, detail=True)
    links = [link for link in graph['links'] if link['label'] == 'mismo elemento']
    assert links
    assert all(link['confidence'] == 'EXTRACTED' for link in links)
    assert graph['metadata']['entity_count'] >= 1


def test_named_buttons_share_design_context_without_merging_work(store):
    session = store.start_session('agy', 'Button design', capture_enabled=True)
    sid = session['id']
    for text in (
        'Necesitamos mejorar el diseño de botones: botón de Jugar',
        'Cambiar el color del botón de Fichas',
        'Ajustar el botón de Ajustes',
        'Cambiar el color del botón de Volver',
    ):
        store.append_message(sid, 'user', text)
    store.process_topics(sid)
    with store._connect() as db:
        entities = {(row[0], row[1]) for row in db.execute('SELECT kind,entity_key FROM entities')}
        topic_count = db.execute('SELECT COUNT(*) FROM topics').fetchone()[0]
        design_links = db.execute("SELECT COUNT(*) FROM topic_relations WHERE relation='tema de diseño'").fetchone()[0]
    assert {('button', 'jugar'), ('button', 'fichas'), ('button', 'ajustes'), ('button', 'volver')} <= entities
    assert ('design_group', 'buttons') in entities
    assert topic_count == 4
    assert design_links >= 1


def test_crm_chats_link_named_controls_and_functionality_across_sessions(store):
    report = store.ingest_turn('agy', 'crm-report', 'CRM', [
        {'role': 'user', 'content': 'Cambia el color del botón del reporte'},
        {'role': 'assistant', 'content': 'Queda pendiente verificar el color'},
    ], consent=True, provider='deterministic')
    operators = store.ingest_turn('codex', 'crm-operators', 'CRM', [
        {'role': 'user', 'content': 'Implementa la funcionalidad del botón de operadores'},
        {'role': 'assistant', 'content': 'La funcionalidad queda en investigación'},
    ], consent=True, provider='deterministic')
    continuation = store.ingest_turn('agy', 'crm-followup', 'CRM', [
        {'role': 'user', 'content': 'Implementa la funcionalidad de operadores'},
    ], consent=True, provider='deterministic')
    entities = {(item['kind'], item['entity_key']) for item in store.entities(requester_agent='dashboard')['entities']}
    assert ('button', 'reporte') in entities
    assert ('report', 'reporte') in entities
    assert ('button', 'operadores') in entities
    assert ('feature', 'operadores') in entities
    with store._connect() as db:
        topic_count = db.execute('SELECT COUNT(*) FROM topics').fetchone()[0]
        operator_topics = db.execute("""SELECT COUNT(DISTINCT te.topic_id) FROM topic_entities te
            JOIN entities e ON e.id=te.entity_id WHERE e.kind='feature' AND e.entity_key='operadores'""").fetchone()[0]
    assert topic_count == 2
    assert operator_topics == 1
    graph = store.topic_graph(requester_agent='dashboard', detail=True, limit=100)
    labels = {link['label'] for link in graph['links']}
    assert {'mismo tipo', 'tema de diseño', 'implementa'} <= labels


def test_python_chats_link_files_and_symbols_without_merging_work(store):
    store.ingest_turn('agy', 'py-report', 'CRM Python', [
        {'role': 'user', 'content': 'Corrige la función calcular_reporte en reports.py'},
        {'role': 'assistant', 'content': 'Queda pendiente probarla'},
    ], consent=True, provider='deterministic')
    store.ingest_turn('codex', 'py-tests', 'CRM Python', [
        {'role': 'user', 'content': 'Agrega una prueba para la función calcular_reporte'},
        {'role': 'assistant', 'content': 'La prueba queda pendiente de ejecución'},
    ], consent=True, provider='deterministic')
    entities = {(item['kind'], item['entity_key']) for item in store.entities(requester_agent='dashboard')['entities']}
    assert ('file', 'reports.py') in entities
    assert ('python_function', 'calcular_reporte') in entities
    graph = store.topic_graph(requester_agent='dashboard', detail=True, limit=100)
    assert any(link['label'] == 'mismo símbolo' for link in graph['links'])
    assert graph['metadata']['topic_count'] == 2


def test_stream_restart_partial_tail_and_exclusions(store, tmp_path):
    from graphtyn.core.history_stream import ingest_jsonl
    path = tmp_path / 'history.jsonl'
    path.write_text('\n'.join(json.dumps({'id': str(i), 'role': 'user' if i % 2 == 0 else 'assistant', 'content': f'Android build {i}'}) for i in range(65)) + '\n' + '{"role":')
    kwargs = dict(provider='codex', agent_id='codex', external_session_id='native', consent=True, explicit_project_selection=True)
    with pytest.raises(InterruptedError):
        ingest_jsonl(store, path, **kwargs, progress=lambda _: False)
    result = ingest_jsonl(store, path, **kwargs)
    assert result['processed'] == 65
    assert result['pending_bytes'] > 0
    repeat = ingest_jsonl(store, path, **kwargs)
    assert repeat['processed'] == 65
    assert len(store.list_messages(result['session_id'])) == 65
    with path.open('a') as f: f.write('"user","content":"Botones"}\n')
    completed = ingest_jsonl(store, path, **kwargs)
    assert completed['processed'] == 66
    assert completed['pending_bytes'] == 0


def test_agy_planner_and_generic_tool_preserve_roles():
    from graphtyn.core.history_import import _role, _content
    assert _role({'source':'MODEL','type':'PLANNER_RESPONSE','content':'Se corrigió Android','thinking':'hidden'}) == 'assistant'
    assert _role({'source':'MODEL','type':'GENERIC','content':'Created At: today\nExit code: 1'}) == 'tool'
    assert _role({'source':'MODEL','type':'GENERIC','content':'untyped'}) is None
    assert _role({'role':'assistant','channel':'analysis','content':'hidden'}) is None
    assert _content({'content':[{'type':'thinking','text':'hidden'},{'type':'text','text':'visible'}]}) == 'visible'
