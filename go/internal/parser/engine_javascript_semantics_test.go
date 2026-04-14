package parser

import (
	"path/filepath"
	"reflect"
	"testing"
)

func TestDefaultEngineParsePathTypeScriptSemanticsAndTypes(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "app", "api", "health", "route.ts")
	writeTestFile(
		t,
		filePath,
		`import { NextRequest, NextResponse } from "next/server";
import express from "express";
import { SSMClient } from "@aws-sdk/client-ssm";

enum Direction {
  Up = "UP",
}

type Handler = (value: string) => string;

const app = express();
const client = new SSMClient({ region: "us-east-1" });

app.get("/health", (_req, _res) => {
  return null;
});

export async function GET(_request: NextRequest) {
  return NextResponse.json({ ok: true });
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

	assertNamedBucketContains(t, got, "enums", "Direction")
	assertNamedBucketContains(t, got, "type_aliases", "Handler")
	assertFrameworksEqual(t, got, "nextjs", "express", "aws")
	assertNestedStringSliceEqual(t, got, "nextjs", "route_verbs", []string{"GET"})
	assertNestedStringSliceEqual(t, got, "nextjs", "route_segments", []string{"api", "health"})
	assertNestedStringValue(t, got, "nextjs", "module_kind", "route")
	assertNestedStringValue(t, got, "nextjs", "runtime_boundary", "server")
	assertNestedStringSliceEqual(
		t,
		got,
		"nextjs",
		"request_response_apis",
		[]string{"NextRequest", "NextResponse"},
	)
	assertNestedStringSliceEqual(t, got, "express", "route_methods", []string{"GET"})
	assertNestedStringSliceEqual(t, got, "express", "route_paths", []string{"/health"})
	assertNestedStringSliceEqual(t, got, "express", "server_symbols", []string{"app"})
	assertNestedStringSliceEqual(t, got, "aws", "services", []string{"ssm"})
	assertNestedStringSliceEqual(t, got, "aws", "client_symbols", []string{"SSMClient"})
}

func TestDefaultEngineParsePathTSXSemanticsAndComponents(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "app", "[locale]", "boats", "page.tsx")
	writeTestFile(
		t,
		filePath,
		`"use client";

import React, { useState } from "react";
import { useToolbarOverflow } from "./hooks/useToolbarOverflow";
import type { Metadata } from "next";

type User = {
  id: string;
};

export async function generateMetadata(): Promise<Metadata> {
  return { title: "Boats" };
}

export default function BoatsPage() {
  const [open, setOpen] = useState(false);
  useToolbarOverflow();
  return <button onClick={() => setOpen(!open)}>{String(open)}</button>;
}
`,
	)

	engine, err := DefaultEngine()
	if err != nil {
		t.Fatalf("DefaultEngine() error = %v, want nil", err)
	}

	got, err := engine.ParsePath(repoRoot, filePath, false, Options{VariableScope: "all"})
	if err != nil {
		t.Fatalf("ParsePath() error = %v, want nil", err)
	}

	assertNamedBucketContains(t, got, "type_aliases", "User")
	assertNamedBucketContains(t, got, "components", "BoatsPage")
	assertFrameworksEqual(t, got, "nextjs", "react")
	assertNestedStringValue(t, got, "react", "boundary", "client")
	assertNestedStringSliceEqual(t, got, "react", "component_exports", []string{"BoatsPage"})
	assertNestedStringSliceEqual(t, got, "react", "hooks_used", []string{"useState", "useToolbarOverflow"})
	assertNestedStringValue(t, got, "nextjs", "module_kind", "page")
	assertNestedStringValue(t, got, "nextjs", "metadata_exports", "dynamic")
	assertNestedStringSliceEqual(t, got, "nextjs", "route_segments", []string{"[locale]", "boats"})
	assertNestedStringValue(t, got, "nextjs", "runtime_boundary", "client")
}

func TestDefaultEngineParsePathJavaScriptFrameworkSemantics(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "server", "routes.jsx")
	writeTestFile(
		t,
		filePath,
		`"use client";

const express = require("express");
const vision = require("@google-cloud/vision");
const router = express.Router();

export function ToolbarButton() {
  const [open, setOpen] = useState(false);
  useToolbarOverflow();
  return open;
}

router.get("/auth/login", login);
router.post("/", createVideo);

const client = new vision.ImageAnnotatorClient();
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

	assertFrameworksEqual(t, got, "express", "gcp", "react")
	assertNestedStringSliceEqual(t, got, "express", "route_methods", []string{"GET", "POST"})
	assertNestedStringSliceEqual(t, got, "express", "route_paths", []string{"/auth/login", "/"})
	assertNestedStringSliceEqual(t, got, "express", "server_symbols", []string{"router"})
	assertNestedStringSliceEqual(t, got, "gcp", "services", []string{"vision"})
	assertNestedStringSliceEqual(t, got, "gcp", "client_symbols", []string{"ImageAnnotatorClient"})
	assertNestedStringValue(t, got, "react", "boundary", "client")
	assertNestedStringSliceEqual(t, got, "react", "component_exports", []string{"ToolbarButton"})
	assertNestedStringSliceEqual(t, got, "react", "hooks_used", []string{"useState", "useToolbarOverflow"})
}

func TestDefaultEngineParsePathJavaScriptDocstringsAndMethodKinds(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "runtime_surface.js")
	writeTestFile(
		t,
		filePath,
		`/** Documented utility. */
function documented(value) {
  return value;
}

class Counter {
  get count() {
    return 1;
  }

  set count(value) {
    this._count = value;
  }

  async load() {
    return Promise.resolve(this.count);
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

	documented := findNamedBucketItem(t, got, "functions", "documented")
	assertStringFieldValue(t, documented, "docstring", "Documented utility.")

	countItems := findAllNamedBucketItems(t, got, "functions", "count")
	if len(countItems) != 2 {
		t.Fatalf("functions.count entries = %#v, want 2 items", countItems)
	}
	assertStringFieldValue(t, countItems[0], "type", "getter")
	assertStringFieldValue(t, countItems[1], "type", "setter")

	load := findNamedBucketItem(t, got, "functions", "load")
	assertStringFieldValue(t, load, "type", "async")
}

func TestDefaultEngineParsePathJSXStatelessComponentSemantics(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "components", "HeroBanner.jsx")
	writeTestFile(
		t,
		filePath,
		`export function HeroBanner() {
  return <section className="hero">Boats</section>;
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

	assertNamedBucketContains(t, got, "components", "HeroBanner")
	assertFrameworksEqual(t, got, "react")
	assertNestedStringValue(t, got, "react", "boundary", "shared")
	assertNestedStringSliceEqual(t, got, "react", "component_exports", []string{"HeroBanner"})
	assertNestedStringSliceEqual(t, got, "react", "hooks_used", []string{})
}

func TestDefaultEngineParsePathTypeScriptDecoratorAndGenericParity(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "decorators.ts")
	writeTestFile(
		t,
		filePath,
		`@sealed
class Demo<T> {}

function identity<T>(value: T): T {
  return value;
}

type Box<T> = { value: T };
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

	assertNamedBucketContains(t, got, "classes", "Demo")
	assertNamedBucketContains(t, got, "functions", "identity")
	assertNamedBucketContains(t, got, "type_aliases", "Box")

	demoClass := findNamedBucketItem(t, got, "classes", "Demo")
	classDecorators, ok := demoClass["decorators"].([]string)
	if !ok {
		t.Fatalf("classes.Demo.decorators = %T, want []string", demoClass["decorators"])
	}
	if !reflect.DeepEqual(classDecorators, []string{"@sealed"}) {
		t.Fatalf("classes.Demo.decorators = %#v, want []string{\"@sealed\"}", classDecorators)
	}
	assertStringSliceFieldValue(t, demoClass, "type_parameters", []string{"T"})

	identityFn := findNamedBucketItem(t, got, "functions", "identity")
	functionDecorators, ok := identityFn["decorators"].([]string)
	if !ok {
		t.Fatalf("functions.identity.decorators = %T, want []string", identityFn["decorators"])
	}
	if len(functionDecorators) != 0 {
		t.Fatalf("functions.identity.decorators = %#v, want []", functionDecorators)
	}
	assertStringSliceFieldValue(t, identityFn, "type_parameters", []string{"T"})

	boxAlias := findNamedBucketItem(t, got, "type_aliases", "Box")
	assertStringSliceFieldValue(t, boxAlias, "type_parameters", []string{"T"})
}

func TestDefaultEngineParsePathTSXJSXComponentUsageParity(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "Widget.tsx")
	writeTestFile(
		t,
		filePath,
		`type WidgetProps = {
  label: string;
};

function ToolbarButton({ label }: WidgetProps) {
  return <button>{label}</button>;
}

export function WidgetPage() {
  return <ToolbarButton label="hello" />;
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

	assertNamedBucketContains(t, got, "type_aliases", "WidgetProps")
	assertNamedBucketContains(t, got, "function_calls", "ToolbarButton")
}

func TestDefaultEngineParsePathTSXClassComponentParity(t *testing.T) {
	t.Parallel()

	repoRoot := t.TempDir()
	filePath := filepath.Join(repoRoot, "src", "LegacyWidget.tsx")
	writeTestFile(
		t,
		filePath,
		`import React from "react";

type LegacyWidgetProps = {
  title: string;
};

export class LegacyWidget extends React.Component<LegacyWidgetProps> {
  render() {
    return <section>{this.props.title}</section>;
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

	assertNamedBucketContains(t, got, "classes", "LegacyWidget")
	assertNamedBucketContains(t, got, "functions", "render")
	assertNamedBucketContains(t, got, "type_aliases", "LegacyWidgetProps")
}

func findNamedBucketItem(t *testing.T, payload map[string]any, key string, name string) map[string]any {
	t.Helper()

	items, ok := payload[key].([]map[string]any)
	if !ok {
		t.Fatalf("%s = %T, want []map[string]any", key, payload[key])
	}
	for _, item := range items {
		itemName, _ := item["name"].(string)
		if itemName == name {
			return item
		}
	}
	t.Fatalf("%s missing item with name %q", key, name)
	return nil
}

func findAllNamedBucketItems(t *testing.T, payload map[string]any, key string, name string) []map[string]any {
	t.Helper()

	items, ok := payload[key].([]map[string]any)
	if !ok {
		t.Fatalf("%s = %T, want []map[string]any", key, payload[key])
	}
	matches := make([]map[string]any, 0)
	for _, item := range items {
		itemName, _ := item["name"].(string)
		if itemName == name {
			matches = append(matches, item)
		}
	}
	return matches
}

func assertFrameworksEqual(t *testing.T, payload map[string]any, want ...string) {
	t.Helper()

	semantics := frameworkSemanticsMap(t, payload)
	got, ok := semantics["frameworks"].([]string)
	if !ok {
		t.Fatalf("framework_semantics.frameworks = %T, want []string", semantics["frameworks"])
	}
	if want == nil {
		want = []string{}
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("frameworks = %#v, want %#v", got, want)
	}
}

func assertNestedStringValue(t *testing.T, payload map[string]any, section string, key string, want string) {
	t.Helper()

	nested := nestedSemanticsSection(t, payload, section)
	got, ok := nested[key].(string)
	if !ok {
		t.Fatalf("framework_semantics.%s.%s = %T, want string", section, key, nested[key])
	}
	if got != want {
		t.Fatalf("framework_semantics.%s.%s = %#v, want %#v", section, key, got, want)
	}
}

func assertNestedStringSliceEqual(
	t *testing.T,
	payload map[string]any,
	section string,
	key string,
	want []string,
) {
	t.Helper()

	nested := nestedSemanticsSection(t, payload, section)
	got, ok := nested[key].([]string)
	if !ok {
		t.Fatalf("framework_semantics.%s.%s = %T, want []string", section, key, nested[key])
	}
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("framework_semantics.%s.%s = %#v, want %#v", section, key, got, want)
	}
}

func frameworkSemanticsMap(t *testing.T, payload map[string]any) map[string]any {
	t.Helper()

	semantics, ok := payload["framework_semantics"].(map[string]any)
	if !ok {
		t.Fatalf("framework_semantics = %T, want map[string]any", payload["framework_semantics"])
	}
	return semantics
}

func nestedSemanticsSection(t *testing.T, payload map[string]any, section string) map[string]any {
	t.Helper()

	semantics := frameworkSemanticsMap(t, payload)
	nested, ok := semantics[section].(map[string]any)
	if !ok {
		t.Fatalf("framework_semantics.%s = %T, want map[string]any", section, semantics[section])
	}
	return nested
}
