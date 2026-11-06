import json
import socket
import sys

import pytest

from graphtyn.core.deployment import service_artifact
from graphtyn.core.listen import bind_socket, browser_host, listen_hosts


def test_hosts_come_from_repeated_or_comma_separated_values():
    assert listen_hosts(None) == ["127.0.0.1"]
    assert listen_hosts("127.0.0.1") == ["127.0.0.1"]
    assert listen_hosts(["127.0.0.1", "192.0.2.10,127.0.0.1"]) == ["127.0.0.1", "192.0.2.10"]
    with pytest.raises(ValueError):
        listen_hosts(["127.0.0.1;rm"])


def test_the_browser_opens_on_loopback_when_the_server_listens_there():
    assert browser_host(["192.0.2.10", "127.0.0.1"]) == "127.0.0.1"
    assert browser_host(["0.0.0.0"]) == "127.0.0.1"
    assert browser_host(["192.0.2.10"]) == "192.0.2.10"


def test_bind_socket_listens_on_loopback():
    sock = bind_socket("127.0.0.1", 0)
    try:
        assert sock.getsockname()[0] == "127.0.0.1" and sock.type == socket.SOCK_STREAM
    finally:
        sock.close()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="IP_FREEBIND is Linux-only")
def test_an_address_whose_interface_is_not_up_yet_can_still_be_bound():
    sock = bind_socket("10.254.254.254", 0)
    sock.close()


def test_a_service_listens_on_every_host_and_needs_tokens_beyond_loopback(tmp_path):
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps({"agent": {"role": "reader"}}), encoding="utf-8")
    hosts = ["127.0.0.1", "192.0.2.10"]

    unit = service_artifact(tmp_path, kind="systemd", output=tmp_path / "u.service", host=hosts, tokens_file=tokens)
    compose = service_artifact(tmp_path, kind="compose", output=tmp_path / "c.yml", host=hosts, tokens_file=tokens)

    assert "serve --host 127.0.0.1 --host 192.0.2.10 --port 9210" in unit.read_text()
    assert 'ports: ["127.0.0.1:9210:9210", "192.0.2.10:9210:9210"]' in compose.read_text()
    with pytest.raises(ValueError, match="tokens-file"):
        service_artifact(tmp_path, kind="systemd", output=tmp_path / "x.service", host=hosts)


def test_serve_and_service_accept_the_host_option_more_than_once():
    from graphtyn.cli_parser import build_parser

    parser = build_parser()
    assert parser.parse_args(["serve", "--host", "127.0.0.1", "--host", "192.0.2.10"]).host == ["127.0.0.1",
                                                                                                  "192.0.2.10"]
    assert parser.parse_args(["serve"]).host is None
    assert parser.parse_args(["service", "install", "--host", "127.0.0.1"]).host == ["127.0.0.1"]
