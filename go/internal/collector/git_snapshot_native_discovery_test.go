package collector

import (
	"context"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/platformcontext/platform-context-graph/go/internal/parser"
)

func TestNativeRepositorySnapshotterDefaultDiscoverySkipsDependencyDirs(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()

	// Source file that should be indexed.
	writeCollectorTestFile(t, filepath.Join(repoRoot, "main.py"), "def main(): pass\n")

	// Files inside dependency dirs that should be skipped by default.
	for _, dir := range []string{
		"node_modules", "vendor", "__pycache__", "site-packages",
		".terraform", ".terragrunt-cache", "dist", "build", "Pods",
		"ansible_collections", ".jenkins", ".yarn",
	} {
		writeCollectorTestFile(t, filepath.Join(repoRoot, dir, "dep.py"), "def dep(): pass\n")
	}
	writeCollectorTestFile(t, filepath.Join(repoRoot, ".yarn", "releases", "yarn-4.13.0.cjs"), "module.exports = {}\n")

	// Files with ignored extensions that should be skipped.
	writeCollectorTestFile(t, filepath.Join(repoRoot, "server.log"), "log line\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "test.out"), "output\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "app.min.js"), "minified\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "style.min.css"), "minified\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "bundle.js.map"), "sourcemap\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "lib.pyc"), "compiled\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, ".pnp.cjs"), "module.exports = {}\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, ".pnp.loader.mjs"), "export default {}\n")

	engine, err := parser.DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v", err)
	}

	resolvedRepoRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		resolvedRepoRoot = repoRoot
	}

	now := time.Date(2026, time.April, 15, 12, 0, 0, 0, time.UTC)
	snapshotter := NativeRepositorySnapshotter{
		Engine: engine,
		Now:    func() time.Time { return now },
	}

	got, err := snapshotter.SnapshotRepository(
		context.Background(),
		SelectedRepository{RepoPath: resolvedRepoRoot},
	)
	if err != nil {
		t.Fatalf("SnapshotOneRepository() error = %v", err)
	}

	// Only main.py should be discovered — all dependency dirs should be pruned.
	if got.FileCount != 1 {
		t.Errorf("FileCount = %d, want 1 (only main.py); dependency dirs were not skipped", got.FileCount)
	}
	for _, entity := range got.ContentEntities {
		if entity.EntityName == "dep" {
			t.Errorf("found entity %q from dependency dir; default ignored dirs not applied", entity.RelativePath)
		}
	}
}

func TestResolveNativeSnapshotFileSetSkipsLargeWebpackBundles(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(t, filepath.Join(repoRoot, ".git", "HEAD"), "ref: refs/heads/main\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "src", "app.js"), "export function app() { return 'source'; }\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "app.js"), largeWebpackBootstrapFixture())

	resolvedRepoRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		resolvedRepoRoot = repoRoot
	}
	registry := parser.DefaultRegistry()
	fileSet, stats, err := resolveNativeSnapshotFileSet(resolvedRepoRoot, registry, NativeRepositorySnapshotter{}.discoveryOptions())
	if err != nil {
		t.Fatalf("resolveNativeSnapshotFileSet() error = %v", err)
	}

	if got, want := len(fileSet.Files), 1; got != want {
		t.Fatalf("file count = %d, want %d; files=%v", got, want, fileSet.Files)
	}
	if got, want := filepath.ToSlash(fileSet.Files[0]), "src/app.js"; !strings.HasSuffix(got, want) {
		t.Fatalf("indexed file = %q, want suffix %q", got, want)
	}
	if got := stats.FilesSkippedByContent["generated-webpack"]; got != 1 {
		t.Fatalf("FilesSkippedByContent[generated-webpack] = %d, want 1", got)
	}
}

func TestResolveNativeSnapshotFileSetSkipsLargeGeneratedJavaScriptBundles(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(t, filepath.Join(repoRoot, ".git", "HEAD"), "ref: refs/heads/main\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "src", "app.js"), "export function app() { return 'source'; }\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "webpack5.js"), largeWebpack5BootstrapFixture())
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "rollup.js"), largeRollupBootstrapFixture())
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "esbuild.js"), largeESBuildBootstrapFixture())
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "parcel.js"), largeParcelBootstrapFixture())

	resolvedRepoRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		resolvedRepoRoot = repoRoot
	}
	registry := parser.DefaultRegistry()
	fileSet, stats, err := resolveNativeSnapshotFileSet(resolvedRepoRoot, registry, NativeRepositorySnapshotter{}.discoveryOptions())
	if err != nil {
		t.Fatalf("resolveNativeSnapshotFileSet() error = %v", err)
	}

	if got, want := len(fileSet.Files), 1; got != want {
		t.Fatalf("file count = %d, want %d; files=%v", got, want, fileSet.Files)
	}
	if got, want := filepath.ToSlash(fileSet.Files[0]), "src/app.js"; !strings.HasSuffix(got, want) {
		t.Fatalf("indexed file = %q, want suffix %q", got, want)
	}
	for reason, want := range map[string]int{
		"generated-webpack": 1,
		"generated-rollup":  1,
		"generated-esbuild": 1,
		"generated-parcel":  1,
	} {
		if got := stats.FilesSkippedByContent[reason]; got != want {
			t.Fatalf("FilesSkippedByContent[%s] = %d, want %d", reason, got, want)
		}
	}
}

func TestResolveNativeSnapshotFileSetSkipsLegacyVendoredLibraries(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	writeCollectorTestFile(t, filepath.Join(repoRoot, ".git", "HEAD"), "ref: refs/heads/main\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "src", "jquery_adapter.js"), "export function adaptJQuery() { return true; }\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "src", "marinus", "library", "Zend", "Gdata", "GroupEntry.php"), "<?php\n/** Zend Framework */\nclass Zend_Gdata_GroupEntry {}\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "jquery.js"), "/* jQuery JavaScript Library v1.12.4 */\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "public", "js", "shadowbox.js"), "/* Shadowbox.js */\n")
	writeCollectorTestFile(t, filepath.Join(repoRoot, "scripts", "fpdf.php"), "<?php\n/* FPDF */\n")

	resolvedRepoRoot, err := filepath.EvalSymlinks(repoRoot)
	if err != nil {
		resolvedRepoRoot = repoRoot
	}
	registry := parser.DefaultRegistry()
	fileSet, stats, err := resolveNativeSnapshotFileSet(resolvedRepoRoot, registry, NativeRepositorySnapshotter{}.discoveryOptions())
	if err != nil {
		t.Fatalf("resolveNativeSnapshotFileSet() error = %v", err)
	}

	if got, want := len(fileSet.Files), 1; got != want {
		t.Fatalf("file count = %d, want %d; files=%v", got, want, fileSet.Files)
	}
	if got, want := filepath.ToSlash(fileSet.Files[0]), "src/jquery_adapter.js"; !strings.HasSuffix(got, want) {
		t.Fatalf("indexed file = %q, want suffix %q", got, want)
	}
	if got := stats.FilesSkippedByContent["vendored-zend-framework"]; got != 1 {
		t.Fatalf("FilesSkippedByContent[vendored-zend-framework] = %d, want 1", got)
	}
	if got := stats.FilesSkippedByContent["vendored-browser-library"]; got != 2 {
		t.Fatalf("FilesSkippedByContent[vendored-browser-library] = %d, want 2", got)
	}
	if got := stats.FilesSkippedByContent["vendored-fpdf"]; got != 1 {
		t.Fatalf("FilesSkippedByContent[vendored-fpdf] = %d, want 1", got)
	}
}

func largeWebpackBootstrapFixture() string {
	header := "/******/ (function(modules) { // webpackBootstrap\n" +
		"/******/ \tvar installedModules = {};\n" +
		"/******/ \tfunction __webpack_require__(moduleId) { return modules[moduleId]; }\n"
	return header + strings.Repeat("var generatedBundleChunk = 1;\n", 12000)
}

func largeWebpack5BootstrapFixture() string {
	header := "/******/ (() => { // webpackBootstrap\n" +
		"/******/ \tvar __webpack_modules__ = ({})\n" +
		"/******/ \tvar __webpack_module_cache__ = {};\n" +
		"/******/ \tfunction __webpack_require__(moduleId) { return __webpack_modules__[moduleId]; }\n"
	return header + strings.Repeat("var generatedBundleChunk = 1;\n", 12000)
}

func largeRollupBootstrapFixture() string {
	header := "var commonjsGlobal = typeof globalThis !== 'undefined' ? globalThis : typeof window !== 'undefined' ? window : global;\n" +
		"function getDefaultExportFromCjs (x) { return x && x.__esModule && Object.prototype.hasOwnProperty.call(x, 'default') ? x['default'] : x; }\n" +
		"function getAugmentedNamespace(n) { var a = Object.create(null); if (n) Object.keys(n).forEach(function (k) { a[k] = n[k]; }); Object.defineProperty(a, '__esModule', { value: true }); return a; }\n" +
		"function commonjsRequire(path) { throw new Error('Could not dynamically require ' + path); }\n"
	return header + strings.Repeat("var generatedBundleChunk = 1;\n", 12000)
}

func largeESBuildBootstrapFixture() string {
	header := "var __defProp = Object.defineProperty;\n" +
		"var __getOwnPropNames = Object.getOwnPropertyNames;\n" +
		"var __commonJS = (cb, mod) => function __require() { return mod || cb((mod = { exports: {} }).exports, mod), mod.exports; };\n" +
		"var __copyProps = (to, from, except, desc) => { if (from && typeof from === 'object') for (let key of __getOwnPropNames(from)) if (!Object.prototype.hasOwnProperty.call(to, key) && key !== except) __defProp(to, key, { get: () => from[key], enumerable: !(desc = Object.getOwnPropertyDescriptor(from, key)) || desc.enumerable }); return to; };\n" +
		"var __toESM = (mod, isNodeMode, target) => (target = mod != null ? Object.create(Object.getPrototypeOf(mod)) : {}, __copyProps(isNodeMode || !mod || !mod.__esModule ? __defProp(target, 'default', { value: mod, enumerable: true }) : target, mod));\n"
	return header + strings.Repeat("var generatedBundleChunk = 1;\n", 12000)
}

func largeParcelBootstrapFixture() string {
	header := "var $parcel$global = typeof globalThis !== 'undefined' ? globalThis : typeof self !== 'undefined' ? self : window;\n" +
		"parcelRequire = (function (modules, cache, entry, globalName) {\n" +
		"function Module(moduleName) { this.id = moduleName; this.bundle = newRequire; this.exports = {}; }\n" +
		"function newRequire(name, jumped) { if(!cache[name]) { var module = cache[name] = new newRequire.Module(name); modules[name][0].call(module.exports, function(x){ return newRequire(modules[name][1][x] || x); }, module, module.exports); } return cache[name].exports; }\n" +
		"newRequire.isParcelRequire = true;\n" +
		"newRequire.Module = Module;\n" +
		"for (var i = 0; i < entry.length; i++) newRequire(entry[i]);\n"
	return header + strings.Repeat("var generatedBundleChunk = 1;\n", 12000)
}
