#!/usr/bin/env python3
"""Test all language parsers and identify any query issues."""

from pathlib import Path
from tempfile import TemporaryDirectory

from platform_context_graph.tools.graph_builder import TreeSitterParser

test_cases = {
    'python': '''
def hello():
    print('world')

class MyClass:
    pass
''',
    'javascript': '''
function hello() {
    console.log('world');
}

class MyClass {
    constructor() {}
}
''',
    'typescript': '''
function hello(): void {
    console.log('world');
}

interface MyInterface {
    name: string;
}
''',
    'go': '''
package main

func hello() {
    println("world")
}

type MyStruct struct {
    Name string
}
''',
    'rust': '''
fn hello() {
    println!("world");
}

struct MyStruct {
    name: String,
}
''',
    'c': '''
#include <stdio.h>

void hello() {
    printf("world");
}

struct MyStruct {
    int value;
};
''',
    'cpp': '''
#include <iostream>

void hello() {
    std::cout << "world";
}

class MyClass {
public:
    int value;
};
''',
    'java': '''
public class Test {
    public void hello() {
        System.out.println("world");
    }
}
''',
    'ruby': '''
def hello
    puts "world"
end

class MyClass
end
''',
    'c_sharp': '''
using System;

class Test {
    void Hello() {
        Console.WriteLine("world");
    }
}
''',
    'dart': '''
void hello() {
    print('world');
}

class MyClass {
  int value = 0;
}
''',
    'perl': '''
package MyModule;
sub hello {
    print "world\\n";
}
1;
'''
}

extensions = {
    'python': '.py',
    'javascript': '.js',
    'typescript': '.ts',
    'go': '.go',
    'rust': '.rs',
    'c': '.c',
    'cpp': '.cpp',
    'java': '.java',
    'ruby': '.rb',
    'c_sharp': '.cs',
    'dart': '.dart',
    'perl': '.pl'
}

def main() -> None:
    """Run parser smoke tests and print a summary."""
    results = {}
    with TemporaryDirectory(prefix="pcg-parser-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        for lang, code in test_cases.items():
            print(f'Testing {lang}...')
            try:
                parser = TreeSitterParser(lang)
                ext = extensions[lang]
                file = temp_root / f'test{ext}'
                file.write_text(code)
                result = parser.parse(file, is_dependency=False)

                funcs = len(result.get('functions', []))
                classes = len(result.get('classes', []))
                results[lang] = {'status': 'OK', 'functions': funcs, 'classes': classes}
                print(f'  ✓ {lang}: {funcs} functions, {classes} classes')
            except Exception as e:
                error_msg = str(e)
                results[lang] = {'status': 'ERROR', 'error': error_msg}
                print(f'  ✗ {lang}: {error_msg[:150]}')

    print('\n' + '='*60)
    print('SUMMARY')
    print('='*60)

    ok_count = sum(1 for r in results.values() if r['status'] == 'OK')
    error_count = sum(1 for r in results.values() if r['status'] == 'ERROR')

    print(f'✓ Working: {ok_count}/{len(results)}')
    print(f'✗ Errors: {error_count}/{len(results)}')

    if error_count > 0:
        print('\nLanguages with errors:')
        for lang, result in results.items():
            if result['status'] == 'ERROR':
                print(f'  - {lang}')


if __name__ == "__main__":
    main()
