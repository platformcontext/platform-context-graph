# Parser Feature Matrix

## Language Parsers

| Language | Parser | Functions | Classes | Interfaces | Traits | Imports | Calls | Variables | Structs | Enums | Macros | Unit Tests | Integration Tests | Fixture |
|----------|--------|-----------|---------|------------|--------|---------|-------|-----------|---------|-------|--------|------------|-------------------|---------|
| Python | PythonTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | - | - | Y | Y | Y |
| Go | GoTreeSitterParser | Y | Y | Y | - | Y | Y | Y | - | - | - | Y | Y | Y |
| TypeScript | TypescriptTreeSitterParser | Y | Y | Y | - | Y | Y | Y | - | Y | - | Y | Y | Y |
| Rust | RustTreeSitterParser | Y | Y | - | Y | Y | Y | - | - | - | - | Y | Y | Y |
| Java | JavaTreeSitterParser | Y | Y | Y | - | Y | Y | Y | - | Y | - | Y | Y | Y |
| C++ | CppTreeSitterParser | Y | Y | - | - | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| C# | CSharpTreeSitterParser | Y | Y | Y | - | Y | Y | - | Y | Y | - | Y | Y | Y |
| C | CTreeSitterParser | Y | - | - | - | Y | Y | Y | Y | Y | Y | Y | Y | Y |
| Scala | ScalaTreeSitterParser | Y | Y | - | Y | Y | Y | Y | - | - | - | Y | Y | Y |
| JavaScript | JavascriptTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | - | - | Y | Y | Y |
| Ruby | RubyTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | - | - | Y | Y | Y |
| Kotlin | KotlinTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | - | - | Y | Y | Y |
| Swift | SwiftTreeSitterParser | Y | Y | - | - | Y | Y | Y | Y | Y | - | Y | Y | Y |
| PHP | PhpTreeSitterParser | Y | Y | Y | Y | Y | Y | Y | - | - | - | Y | Y | Y |
| Perl | PerlTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | - | - | Y | Y | Y |
| Elixir | ElixirTreeSitterParser | Y | Y | - | - | Y | Y | - | - | - | - | Y | Y | Y |
| Haskell | HaskellTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | - | - | Y | Y | Y |
| Dart | DartTreeSitterParser | Y | Y | - | - | Y | Y | Y | - | Y | - | Y | Y | Y |
| TSX | TypescriptJSXTreeSitterParser | Y | Y | Y | - | Y | Y | Y | - | - | - | - | - | Y |

**Legend:** Y = supported, - = not applicable or not extracted

## IaC Parsers

| Tool | Parser | Resources | Variables | Outputs | Modules | Unit Tests | Integration Tests | Fixture |
|------|--------|-----------|-----------|---------|---------|------------|-------------------|---------|
| Terraform | HCLTerraformParser | Y | Y | Y | Y | Y | Y | Y |
| Terragrunt | HCLTerraformParser | Y (configs) | - | - | - | Y | Y | Y |
| Helm | InfraYAMLParser | Charts + Values | - | - | - | Y | Y | Y |
| Kustomize | InfraYAMLParser | Overlays | - | - | - | Y | Y | Y |
| ArgoCD | InfraYAMLParser | Apps + AppSets | - | - | - | Y | Y | Y |
| Crossplane | InfraYAMLParser | XRDs + Compositions + Claims | - | - | - | Y | Y | Y |
| Kubernetes | InfraYAMLParser | K8s Resources | - | - | - | Y | Y | Y |
| CloudFormation | InfraYAMLParser | CFN Resources | Parameters | Outputs | - | Y | Y | Y |

## Test Counts

| Category | Count |
|----------|-------|
| Unit tests (passed) | 188 |
| Unit tests (xfail) | 15 |
| Unit tests (total) | 203 |
| Integration tests | 83 |
| Fixture repos | 27 |
| Spec docs | 28 |
