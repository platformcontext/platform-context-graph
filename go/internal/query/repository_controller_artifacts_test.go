package query

import "testing"

func TestBuildRepositoryControllerArtifactsExtractsJenkinsPipelineSignals(t *testing.T) {
	t.Parallel()

	got := buildRepositoryControllerArtifacts("controller-repo", []FileContent{
		{
			RelativePath: "Jenkinsfile",
			Content: `@Library('pipelines@v2') _
library identifier: 'shared-controllers@main'
pipelineDeploy(
  use_configd: true,
  entry_point: 'dist/app.js',
  pre_deploy: { pipe, params ->
    sh 'ansible-playbook deploy.yml -i inventory/prod.ini'
  }
)
`,
		},
		{
			RelativePath: "scripts/deploy.groovy",
			Content: `library 'ignored'
pipelineDeploy(entry_point: 'dist/worker.js')
`,
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryControllerArtifacts() = nil, want controller_artifacts")
	}

	artifacts := mapSliceValue(got, "controller_artifacts")
	if len(artifacts) != 2 {
		t.Fatalf("len(controller_artifacts) = %d, want 2", len(artifacts))
	}

	first := artifacts[0]
	if got, want := first["path"], "Jenkinsfile"; got != want {
		t.Fatalf("controller_artifacts[0].path = %#v, want %#v", got, want)
	}
	if got, want := first["controller_kind"], "jenkins_pipeline"; got != want {
		t.Fatalf("controller_artifacts[0].controller_kind = %#v, want %#v", got, want)
	}
	if got, want := first["use_configd"], true; got != want {
		t.Fatalf("controller_artifacts[0].use_configd = %#v, want %#v", got, want)
	}
	if got, want := first["has_pre_deploy"], true; got != want {
		t.Fatalf("controller_artifacts[0].has_pre_deploy = %#v, want %#v", got, want)
	}

	sharedLibraries := first["shared_libraries"].([]string)
	if len(sharedLibraries) != 2 || sharedLibraries[0] != "pipelines" || sharedLibraries[1] != "shared-controllers" {
		t.Fatalf("controller_artifacts[0].shared_libraries = %#v, want [pipelines shared-controllers]", sharedLibraries)
	}

	pipelineCalls := first["pipeline_calls"].([]string)
	if len(pipelineCalls) != 1 || pipelineCalls[0] != "pipelineDeploy" {
		t.Fatalf("controller_artifacts[0].pipeline_calls = %#v, want [pipelineDeploy]", pipelineCalls)
	}

	entryPoints := first["entry_points"].([]string)
	if len(entryPoints) != 1 || entryPoints[0] != "dist/app.js" {
		t.Fatalf("controller_artifacts[0].entry_points = %#v, want [dist/app.js]", entryPoints)
	}

	second := artifacts[1]
	if got, want := second["path"], "scripts/deploy.groovy"; got != want {
		t.Fatalf("controller_artifacts[1].path = %#v, want %#v", got, want)
	}
	if got, want := second["controller_kind"], "jenkins_pipeline"; got != want {
		t.Fatalf("controller_artifacts[1].controller_kind = %#v, want %#v", got, want)
	}
	if _, ok := second["use_configd"]; ok {
		t.Fatalf("controller_artifacts[1].use_configd present, want omitted")
	}
	if got, want := second["has_pre_deploy"], false; got != want {
		t.Fatalf("controller_artifacts[1].has_pre_deploy = %#v, want %#v", got, want)
	}

	hints := mapSliceValue(first, "ansible_playbook_hints")
	if len(hints) != 1 {
		t.Fatalf("controller_artifacts[0].ansible_playbook_hints = %#v, want one row", first["ansible_playbook_hints"])
	}
	if got, want := hints[0]["playbook"], "deploy.yml"; got != want {
		t.Fatalf("ansible_playbook_hints[0].playbook = %#v, want %#v", got, want)
	}
}

func TestBuildRepositoryControllerArtifactsIgnoresGenericGroovyScripts(t *testing.T) {
	t.Parallel()

	got := buildRepositoryControllerArtifacts("controller-repo", []FileContent{
		{
			RelativePath: "scripts/helpers.groovy",
			Content:      "println 'helper'",
		},
	})
	if got != nil {
		t.Fatalf("buildRepositoryControllerArtifacts() = %#v, want nil", got)
	}
}
