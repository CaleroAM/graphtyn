from graphtyn.core.console import configure_utf8_stdio


class FakeStream:
    def __init__(self):
        self.calls = []

    def reconfigure(self, **kwargs):
        self.calls.append(kwargs)


def test_windows_stdio_is_reconfigured_as_utf8():
    stdout, stderr = FakeStream(), FakeStream()
    configure_utf8_stdio(stdout=stdout, stderr=stderr, platform_name="nt")
    assert stdout.calls == stderr.calls == [{"encoding": "utf-8", "errors": "replace"}]


def test_non_windows_stdio_is_untouched():
    stdout, stderr = FakeStream(), FakeStream()
    configure_utf8_stdio(stdout=stdout, stderr=stderr, platform_name="posix")
    assert stdout.calls == stderr.calls == []
