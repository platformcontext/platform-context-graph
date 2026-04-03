"""Tests for the Perl parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.parsers.languages.perl import PerlTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def perl_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("perl"):
        pytest.skip("Perl tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "perl"
    wrapper.language = manager.get_language_safe("perl")
    wrapper.parser = manager.create_parser("perl")
    return PerlTreeSitterParser(wrapper)


def test_parse_subroutines(perl_parser, temp_test_dir):
    code = """use strict;
use warnings;

sub greet {
    my ($name) = @_;
    return "Hello, $name!";
}

sub add {
    my ($a, $b) = @_;
    return $a + $b;
}
"""
    f = temp_test_dir / "funcs.pl"
    f.write_text(code)
    result = perl_parser.parse(f)

    funcs = result.get("functions", [])
    assert len(funcs) >= 2
    names = [fn["name"] for fn in funcs]
    assert "greet" in names
    assert "add" in names


def test_parse_packages(perl_parser, temp_test_dir):
    code = """package Animal;

sub new {
    my ($class, %args) = @_;
    return bless { name => $args{name} }, $class;
}

sub name { return $_[0]->{name} }

1;
"""
    f = temp_test_dir / "Animal.pl"
    f.write_text(code)
    result = perl_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Animal" in names


def test_parse_imports(perl_parser, temp_test_dir):
    code = """use strict;
use warnings;
use File::Basename;
use List::Util qw(sum reduce);
"""
    f = temp_test_dir / "imports.pl"
    f.write_text(code)
    result = perl_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 3


def test_parse_function_calls(perl_parser, temp_test_dir):
    code = """sub demo {
    print "hello\\n";
    my @sorted = sort @items;
    my $len = length("test");
}
"""
    f = temp_test_dir / "calls.pl"
    f.write_text(code)
    result = perl_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_variables(perl_parser, temp_test_dir):
    code = """my $name = "World";
my @numbers = (1, 2, 3);
my %config = (host => "localhost", port => 8080);
"""
    f = temp_test_dir / "vars.pl"
    f.write_text(code)
    result = perl_parser.parse(f)

    variables = result.get("variables", [])
    assert len(variables) >= 1


def test_result_structure(perl_parser, temp_test_dir):
    code = "sub placeholder {}\n"
    f = temp_test_dir / "minimal.pl"
    f.write_text(code)
    result = perl_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "perl"
    assert "is_dependency" in result


def test_parse_empty_file(perl_parser, temp_test_dir):
    f = temp_test_dir / "empty.pl"
    f.write_text("")
    result = perl_parser.parse(f)
    assert len(result.get("functions", [])) == 0
