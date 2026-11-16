"""A scoped project indexes only its included paths and does not own unrelated subdirectories."""
import json

from graphtyn.core.ast_parser import ASTParser
from graphtyn.core.index_scope import IndexScope, covers, is_secret_path
from graphtyn.core.openclaw_project_routing import _workspace_target
from graphtyn.core.prompt_context import _indexed_root
from graphtyn.core.storage import project_store_dir
from graphtyn.core.tool_guard import project_root

RULES = [".bashrc", "nixos/", ".config/nvim/**/*.lua", "!nixos/hardware.nix"]


def _home(tmp_path):
    home = tmp_path / "home"
    files = {
        ".bashrc": "export EDITOR=nvim\n",
        "nixos/configuration.nix": "{ pkgs, ... }: {\n  networking.hostName = \"box\";\n}\n",
        "nixos/hardware.nix": "{ }\n",
        "nixos/build/out.nix": "{ }\n",
        ".config/nvim/lua/init.lua": "vim.opt.number = true\n",
        ".config/nvim/lua/node_modules/x.lua": "return 1\n",
        ".config/other/settings.json": "{}\n",
        ".ssh/config": "Host box\n",
        "nixos/secrets.nix": "{ }\n",
        "Documentos/app/main.py": "def main():\n    return 1\n",
        "Downloads/notes.md": "# notes\n",
    }
    for relative, text in files.items():
        (home / relative).parent.mkdir(parents=True, exist_ok=True)
        (home / relative).write_text(text, encoding="utf-8")
    (home / "nixos" / "logo.bin").write_bytes(b"\x00\x01binary")
    return home


def _files(graph):
    return sorted(node["id"][5:] for node in graph["nodes"] if node["id"].startswith("file:"))


def test_a_scope_indexes_only_its_config_files(tmp_path):
    home = _home(tmp_path)

    graph = ASTParser().scan_directory(home, respect_git=False, scope=IndexScope(RULES))

    # Hidden and extensionless config is read; other projects, secrets, binaries and builds are not.
    assert _files(graph) == [".bashrc", ".config/nvim/lua/init.lua", "nixos/configuration.nix"]
    assert any(node.get("file") == "nixos/configuration.nix" for node in graph["nodes"]
               if node.get("kind") == "documentation_section")


def test_without_a_scope_the_directory_is_indexed_as_before(tmp_path):
    home = _home(tmp_path)

    files = _files(ASTParser().scan_directory(home, respect_git=False, scope=IndexScope()))

    assert "Documentos/app/main.py" in files and ".bashrc" not in files


def test_the_walk_does_not_enter_unreachable_directories(tmp_path):
    home = _home(tmp_path)
    scope = IndexScope(RULES)

    walked = {path.relative_to(home).parts[0] for path in scope.walk(home, lambda name: name.startswith("."))}

    assert walked <= {".bashrc", "nixos", ".config"}
    assert not scope.reaches("Documentos") and scope.reaches(".config") and scope.reaches("nixos/modules")


def test_secret_stores_are_never_in_scope():
    assert is_secret_path(".ssh/config") and is_secret_path(".config/gh/hosts.yml")
    assert is_secret_path("nixos/secrets.nix") and is_secret_path("keys/server.pem")
    assert not is_secret_path("nixos/configuration.nix")


def test_a_scoped_home_does_not_own_unrelated_subdirectories(tmp_path, monkeypatch):
    graphtyn_home = tmp_path / "graphtyn-home"
    monkeypatch.setenv("GRAPHTYN_HOME", str(graphtyn_home))
    home = _home(tmp_path)
    store = project_store_dir(graphtyn_home, home)
    (store / "index.json").write_text("{}", encoding="utf-8")
    (store / "config.json").write_text(json.dumps({"include": RULES}), encoding="utf-8")
    elsewhere = home / "Documentos" / "app"

    assert covers(home, home) and covers(home, home / "nixos") and covers(home, home / ".config")
    assert not covers(home, elsewhere) and not covers(home, home / ".ssh")
    assert project_root(str(home / "nixos")) == home.resolve()
    assert project_root(str(elsewhere)) is None
    assert _indexed_root(str(elsewhere)) is None and _indexed_root(str(home)) == home.resolve()
    targets = [{"path": str(home.resolve()), "name": "home"}]
    assert _workspace_target(str(elsewhere), targets) is None
    assert _workspace_target(str(home / "nixos"), targets) == targets[0]

    (store / "config.json").write_text("{}", encoding="utf-8")
    assert project_root(str(elsewhere)) == home.resolve()


def test_a_dropped_directory_is_not_walked_unless_a_rule_reaches_inside(tmp_path):
    scope = IndexScope([".config/**", "!.config/unity3d/", "!.config/Brave/", ".config/Brave/prefs.json"])

    assert not scope.reaches(".config/unity3d") and not scope.reaches(".config/unity3d/cache")
    assert scope.reaches(".config/Brave") and scope.reaches(".config/hypr")
    assert scope.includes(".config/hypr/hyprland.conf") and not scope.includes(".config/unity3d/a.json")
