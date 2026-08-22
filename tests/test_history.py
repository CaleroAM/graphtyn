import tempfile
from pathlib import Path
from graphtyn.core.history import HistoryTracker

def test_history_tracker_log_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        ht = HistoryTracker(workspace)

        obs_id = ht.log_event("session_1", "blast_radius", "Evaluación de radio de impacto para ASTParser", {"symbol": "ASTParser"})
        assert obs_id > 0

        res = ht.search_events("blast_radius")
        assert len(res) == 1
        assert res[0]["summary"] == "Evaluación de radio de impacto para ASTParser"

        timeline = ht.get_timeline("session_1")
        assert len(timeline) == 1

        obs = ht.get_observation(obs_id)
        assert obs["details"]["symbol"] == "ASTParser"
