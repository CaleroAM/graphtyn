import json
import os
import subprocess
import sys
from pathlib import Path
import pytest
from graphtyn.core.shared_memory import SharedMemoryStore
from graphtyn.api import main as api
from graphtyn.core.topic_contracts import dispatch_topic, TOPIC_TOOLS


def test_topic_contracts_api_cli_and_mcp(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAPHTYN_HOME', str(tmp_path / 'home'))
    monkeypatch.delenv('GRAPHTYN_MEMORY_TOKENS', raising=False)
    monkeypatch.delenv('GRAPHTYN_MEMORY_HTTP_TOKEN', raising=False)
    monkeypatch.delenv('GRAPHTYN_MCP_TOKEN', raising=False)
    api._RATE_EVENTS.clear()
    store = SharedMemoryStore(tmp_path / 'project')
    result = store.ingest_turn('codex','native','Textures',[{'role':'user','content':'Texturas del museo'},{'role':'assistant','content':'Se corrigió el material'}],consent=True,provider='deterministic')
    topic = store.topics()['topics'][0]['id']
    assert len(TOPIC_TOOLS) == 9
    assert dispatch_topic(store,'memory_topic',{'topic_id':topic})['episodes']
    assert api.memory_topics(str(store.workspace), authorization=None)['topics'][0]['id'] == topic
    reference = store.topics()['topics'][0]['reference']
    assert api.memory_node(str(store.workspace), reference=reference, authorization=None)['node_id'] == topic
    args = [sys.executable,'-m','graphtyn.cli','memory','topics','Texturas','--path',str(store.workspace)]
    cli = subprocess.run(args, capture_output=True, text=True, check=True)
    assert json.loads(cli.stdout)['topics'][0]['id'] == topic
    runner = 'from pathlib import Path; from graphtyn.mcp_server import run_mcp_server; run_mcp_server(Path('+repr(str(store.workspace))+'))'
    request = {'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'memory_topic','arguments':{'topic_id':topic,'requester_agent':'codex'}}}
    mcp = subprocess.run([sys.executable,'-c',runner],input=json.dumps(request)+'\n',capture_output=True,text=True,check=True)
    body = json.loads(mcp.stdout)['result']
    assert not body.get('isError')
    assert json.loads(body['content'][0]['text'])['topic']['id'] == topic


def test_relation_review_http_contract(tmp_path, monkeypatch):
    monkeypatch.delenv('GRAPHTYN_MEMORY_HTTP_TOKEN', raising=False)
    store = SharedMemoryStore(tmp_path / 'project')
    a = store.start_session('agy', 'a', capture_enabled=True)['id']
    b = store.start_session('agy', 'b', capture_enabled=True)['id']
    store.append_message(a, 'user', 'Android botones textura interfaz')
    store.append_message(b, 'user', 'Android botones textura navegación')
    store.process_topics(a); store.process_topics(b)
    candidate = store.relation_candidates(requester_agent='agy')['candidates'][0]
    response = api.memory_relation_review({'path': str(store.workspace), 'relation_id': candidate['id'], 'status': 'rejected', 'requester_agent': 'agy', 'reason': 'Son asuntos distintos'}, authorization=None)
    assert response['status'] == 'rejected'


def test_topic_api_project_scope_and_writer_role(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAPHTYN_MEMORY_TOKENS', json.dumps({'reader':{'role':'reader','projects':[str(tmp_path/'allowed')]}}))
    api._RATE_EVENTS.clear()
    denied=api.memory_topics(str(tmp_path/'other'),authorization='Bearer reader')
    assert denied.status_code == 403
    denied=api.memory_topic_update({'path':str(tmp_path/'allowed'),'topic_id':'unknown','reason':'test'}, authorization='Bearer reader')
    assert denied.status_code == 403


def test_entity_interfaces_return_named_controls(tmp_path, monkeypatch):
    monkeypatch.setenv('GRAPHTYN_HOME', str(tmp_path / 'home'))
    store = SharedMemoryStore(tmp_path / 'project')
    session = store.start_session('agy', 'UI', capture_enabled=True)
    store.append_message(session['id'], 'user', 'Cambia el diseño del botón de Jugar')
    store.process_topics(session['id'])
    entity = store.entities('Jugar', requester_agent='dashboard')['entities'][0]
    assert entity['entity_key'] == 'jugar'
    detail = dispatch_topic(store, 'memory_entity', {'entity_id': entity['id'], 'requester_agent': 'dashboard'})
    assert detail['topics']
    assert dispatch_topic(store, 'memory_entities', {'query': 'jugar', 'requester_agent': 'dashboard'})['entities']
    assert api.memory_entity(str(store.workspace), entity_id=entity['id'], requester_agent='dashboard', authorization=None)['entity']['entity_key'] == 'jugar'
