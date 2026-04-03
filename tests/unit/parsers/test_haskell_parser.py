"""Tests for the Haskell parser."""

from unittest.mock import MagicMock

import pytest

from platform_context_graph.tools.languages.haskell import HaskellTreeSitterParser
from platform_context_graph.utils.tree_sitter_manager import get_tree_sitter_manager


@pytest.fixture(scope="module")
def haskell_parser():
    manager = get_tree_sitter_manager()
    if not manager.is_language_available("haskell"):
        pytest.skip("Haskell tree-sitter grammar not available")
    wrapper = MagicMock()
    wrapper.language_name = "haskell"
    wrapper.language = manager.get_language_safe("haskell")
    wrapper.parser = manager.create_parser("haskell")
    return HaskellTreeSitterParser(wrapper)


def test_parse_functions(haskell_parser, temp_test_dir):
    code = """module Basic where

greet :: String -> String
greet name = "Hello, " ++ name ++ "!"

add :: Int -> Int -> Int
add a b = a + b

classify :: Int -> String
classify n
  | n < 0     = "negative"
  | n == 0    = "zero"
  | otherwise = "positive"
"""
    f = temp_test_dir / "Basic.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    funcs = result.get("functions", [])
    assert len(funcs) >= 2
    names = [fn["name"] for fn in funcs]
    assert "greet" in names or "add" in names


def test_parse_data_types(haskell_parser, temp_test_dir):
    code = """module Types where

data Shape
  = Circle Double
  | Rectangle Double Double
  | Triangle Double Double Double
  deriving (Show, Eq)

data Person = Person
  { personName :: String
  , personAge  :: Int
  } deriving (Show)

newtype Name = Name String deriving (Show)
"""
    f = temp_test_dir / "Types.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Shape" in names or "Person" in names


def test_parse_type_classes(haskell_parser, temp_test_dir):
    code = """module Classes where

class Describable a where
  describe :: a -> String

instance Describable Int where
  describe n = "Int: " ++ show n
"""
    f = temp_test_dir / "Classes.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    classes = result.get("classes", [])
    names = [c["name"] for c in classes]
    assert "Describable" in names


def test_parse_imports(haskell_parser, temp_test_dir):
    code = """module Imports where

import Data.List (sort, nub)
import Data.Char (toUpper)
import qualified Data.Map as Map
"""
    f = temp_test_dir / "Imports.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    imports = result.get("imports", [])
    assert len(imports) >= 3


def test_parse_variables(haskell_parser, temp_test_dir):
    code = """module Vars where

version :: String
version = "1.0.0"

maxRetries :: Int
maxRetries = 3
"""
    f = temp_test_dir / "Vars.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    # Variables or functions (Haskell treats top-level bindings similarly)
    total = len(result.get("variables", [])) + len(result.get("functions", []))
    assert total >= 2


def test_parse_function_calls(haskell_parser, temp_test_dir):
    code = """module Calls where

demo :: IO ()
demo = do
  putStrLn "hello"
  let xs = [1, 2, 3]
  print (map (*2) xs)
"""
    f = temp_test_dir / "Calls.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    calls = result.get("function_calls", [])
    assert len(calls) >= 1


def test_parse_higher_order(haskell_parser, temp_test_dir):
    code = """module HOF where

applyTwice :: (a -> a) -> a -> a
applyTwice f x = f (f x)

pipeline :: [Int] -> [Int]
pipeline = filter even . map (*2) . filter (>0)
"""
    f = temp_test_dir / "HOF.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    funcs = result.get("functions", [])
    names = [fn["name"] for fn in funcs]
    assert "applyTwice" in names or "pipeline" in names


def test_result_structure(haskell_parser, temp_test_dir):
    code = "module Minimal where\n\nx = 1\n"
    f = temp_test_dir / "Minimal.hs"
    f.write_text(code)
    result = haskell_parser.parse(f)

    assert result["path"] == str(f)
    assert result["lang"] == "haskell"
    assert "is_dependency" in result


def test_parse_empty_file(haskell_parser, temp_test_dir):
    f = temp_test_dir / "Empty.hs"
    f.write_text("")
    result = haskell_parser.parse(f)
    assert len(result.get("functions", [])) == 0
