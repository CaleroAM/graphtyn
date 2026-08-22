from graphtyn.core.benchmark import syntactically_complete_answer


def test_completion_detector_flags_short_mid_section_answer():
    assert not syntactically_complete_answer("## Verificación\nLa firma usa TimestampSigner y después")
    assert syntactically_complete_answer("Respuesta breve pero completa.")
    assert syntactically_complete_answer("x" * 500)
