package parser

import (
	"path/filepath"
	"testing"
)

func TestDefaultEngineParsePathJava(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "App.java")
	writeTestFile(
		t,
		filePath,
		`import java.util.List;

@Logged
public class App {
    private String name;

    public App(String name) {
        this.name = name;
    }

    public String greet() {
        System.out.println(name);
        return name;
    }
}

interface Runner {
    String run();
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	if got["lang"] != "java" {
		t.Fatalf("lang = %#v, want %#v", got["lang"], "java")
	}

	assertNamedBucketContains(t, got, "classes", "App")
	assertNamedBucketContains(t, got, "interfaces", "Runner")
	assertNamedBucketContains(t, got, "functions", "greet")
	assertNamedBucketContains(t, got, "variables", "name")
	assertNamedBucketContains(t, got, "imports", "java.util.List")
	assertNamedBucketContains(t, got, "function_calls", "println")
}

func TestDefaultEngineParsePathCSharp(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Service.cs")
	writeTestFile(
		t,
		filePath,
		`using System;

public interface IService {
    string Execute(string input);
}

public record Request(string Value);

public class Service : IService {
    public string Name { get; set; } = "default";

    public string Execute(string input) {
        Console.WriteLine(input);
        var request = new Request(input);
        return request.Value;
    }
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	if got["lang"] != "c_sharp" {
		t.Fatalf("lang = %#v, want %#v", got["lang"], "c_sharp")
	}

	assertNamedBucketContains(t, got, "classes", "Service")
	assertNamedBucketContains(t, got, "interfaces", "IService")
	assertNamedBucketContains(t, got, "records", "Request")
	assertNamedBucketContains(t, got, "properties", "Name")
	assertNamedBucketContains(t, got, "functions", "Execute")
	assertNamedBucketContains(t, got, "imports", "System")
	assertNamedBucketContains(t, got, "function_calls", "WriteLine")
	assertNamedBucketContains(t, got, "function_calls", "Request")
}

func TestDefaultEngineParsePathScala(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "Service.scala")
	writeTestFile(
		t,
		filePath,
		`import scala.collection.mutable

trait Runner {
  def run(): String
}

class Service(val name: String) extends Runner {
  def run(): String = {
    println(name)
    name
  }
}

object Bootstrap {
  val version = "1.0.0"
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	if got["lang"] != "scala" {
		t.Fatalf("lang = %#v, want %#v", got["lang"], "scala")
	}

	assertNamedBucketContains(t, got, "classes", "Service")
	assertNamedBucketContains(t, got, "classes", "Bootstrap")
	assertNamedBucketContains(t, got, "traits", "Runner")
	assertNamedBucketContains(t, got, "functions", "run")
	assertNamedBucketContains(t, got, "variables", "version")
	assertNamedBucketContains(t, got, "imports", "scala.collection.mutable")
	assertNamedBucketContains(t, got, "function_calls", "println")
}

func TestDefaultEnginePreScanPathsManagedOO(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	javaPath := filepath.Join(repoRoot, "App.java")
	csharpPath := filepath.Join(repoRoot, "Service.cs")
	scalaPath := filepath.Join(repoRoot, "Bootstrap.scala")

	writeTestFile(
		t,
		javaPath,
		`public class App {
    public String greet() {
        return "hi";
    }
}

interface Runner {}
`,
	)
	writeTestFile(
		t,
		csharpPath,
		`public interface IService {
    string Execute(string input);
}

public class Service : IService {
    public string Execute(string input) {
        return input;
    }
}
`,
	)
	writeTestFile(
		t,
		scalaPath,
		`trait Runner {
  def run(): String
}

object Bootstrap {
  def main(): String = "ready"
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.PreScanPaths([]string{javaPath, csharpPath, scalaPath})
	if err != nil {
		t.Fatalf("PreScanPaths() error = %v, want nil", err)
	}

	assertPrescanContains(t, got, "App", javaPath)
	assertPrescanContains(t, got, "Runner", javaPath)
	assertPrescanContains(t, got, "greet", javaPath)
	assertPrescanContains(t, got, "IService", csharpPath)
	assertPrescanContains(t, got, "Service", csharpPath)
	assertPrescanContains(t, got, "Execute", csharpPath)
	assertPrescanContains(t, got, "Runner", scalaPath)
	assertPrescanContains(t, got, "Bootstrap", scalaPath)
	assertPrescanContains(t, got, "main", scalaPath)
}
