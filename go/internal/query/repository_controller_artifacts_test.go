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
			Content:      "library 'ignored'",
		},
	})
	if got == nil {
		t.Fatal("buildRepositoryControllerArtifacts() = nil, want controller_artifacts")
	}

	artifacts := mapSliceValue(got, "controller_artifacts")
	if len(artifacts) != 1 {
		t.Fatalf("len(controller_artifacts) = %d, want 1", len(artifacts))
	}

	row := artifacts[0]
	if got, want := row["path"], "Jenkinsfile"; got != want {
		t.Fatalf("controller_artifacts[0].path = %#v, want %#v", got, want)
	}
	if got, want := row["controller_kind"], "jenkins_pipeline"; got != want {
		t.Fatalf("controller_artifacts[0].controller_kind = %#v, want %#v", got, want)
	}
	if got, want := row["use_configd"], true; got != want {
		t.Fatalf("controller_artifacts[0].use_configd = %#v, want %#v", got, want)
	}
	if got, want := row["has_pre_deploy"], true; got != want {
		t.Fatalf("controller_artifacts[0].has_pre_deploy = %#v, want %#v", got, want)
	}

	sharedLibraries := row["shared_libraries"].([]string)
	if len(sharedLibraries) != 2 || sharedLibraries[0] != "pipelines" || sharedLibraries[1] != "shared-controllers" {
		t.Fatalf("controller_artifacts[0].shared_libraries = %#v, want [pipelines shared-controllers]", sharedLibraries)
	}

	pipelineCalls := row["pipeline_calls"].([]string)
	if len(pipelineCalls) != 1 || pipelineCalls[0] != "pipelineDeploy" {
		t.Fatalf("controller_artifacts[0].pipeline_calls = %#v, want [pipelineDeploy]", pipelineCalls)
	}

	entryPoints := row["entry_points"].([]string)
	if len(entryPoints) != 1 || entryPoints[0] != "dist/app.js" {
		t.Fatalf("controller_artifacts[0].entry_points = %#v, want [dist/app.js]", entryPoints)
	}

	hints := mapSliceValue(row, "ansible_playbook_hints")
	if len(hints) != 1 {
		t.Fatalf("controller_artifacts[0].ansible_playbook_hints = %#v, want one row", row["ansible_playbook_hints"])
	}
	if got, want := hints[0]["playbook"], "deploy.yml"; got != want {
		t.Fatalf("ansible_playbook_hints[0].playbook = %#v, want %#v", got, want)
	}
}
