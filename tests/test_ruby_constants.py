"""Ruby object creation and constant lookup: `X.new` reaches `initialize`, `A::B` the caller's nesting."""
from graphtyn.core.ast_parser import ASTParser


def _calls(root, source):
    (root / "lib").mkdir()
    (root / "lib" / "a.rb").write_text(source, encoding="utf-8")
    graph = ASTParser().scan_directory(root, respect_git=False)
    nodes = {node["id"]: node for node in graph["nodes"]}
    label = lambda node_id: f"{nodes[node_id].get('namespace') or ''}|{nodes[node_id].get('container')}.{nodes[node_id].get('name')}"  # noqa: E731
    return {(label(link["source"]), label(link["target"]), link.get("confidence"))
            for link in graph["links"] if link.get("label") == "llama"}


def test_new_reaches_initialize_and_types_a_chained_call(tmp_path):
    calls = _calls(tmp_path, "class Reflection\n  def initialize(name); end\nend\n"
                             "class Builder\n  def build; Reflection.new(:a); end\nend\n"
                             "class Base\n  def save; Builder.new.build; end\nend\n")
    assert ("|Builder.build", "|Reflection.initialize", "EXTRACTED") in calls
    assert ("|Base.save", "|Builder.build", "EXTRACTED") in calls


def test_a_constant_resolves_through_the_callers_nesting(tmp_path):
    calls = _calls(tmp_path, "module ActiveRecord\n  module Associations\n    class Builder\n      def build; end\n"
                             "    end\n  end\nend\nmodule ActionMailer\n  class Builder\n    def build; end\n  end\n"
                             "  class Base\n    def deliver; Builder.new.build; end\n  end\nend\n"
                             "class ActiveRecord::Base\n  def save; Associations::Builder.new.build; end\nend\n")
    assert ("ActionMailer|Base.deliver", "ActionMailer|Builder.build", "EXTRACTED") in calls
    assert ("|ActiveRecord::Base.save", "ActiveRecord::Associations|Builder.build", "EXTRACTED") in calls
    assert not any(source.endswith("deliver") and "Associations" in target for source, target, _ in calls)


def test_a_compact_class_and_its_own_new_keep_their_calls(tmp_path):
    calls = _calls(tmp_path, "class ActiveStorage::Blob\n  def self.service; end\nend\n"
                             "class Relation\n  def self.new(klass); end\nend\n"
                             "class MirrorJob\n  def perform; ActiveStorage::Blob.service; Relation.new(1); end\nend\n")
    assert ("|MirrorJob.perform", "|ActiveStorage::Blob.service", "EXTRACTED") in calls
    assert ("|MirrorJob.perform", "|Relation.new", "EXTRACTED") in calls
