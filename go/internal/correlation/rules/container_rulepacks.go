package rules

// ContainerRulePacks returns the first-party rule packs for the initial container slice.
func ContainerRulePacks() []RulePack {
	return []RulePack{
		DockerfileRulePack(),
		GitHubActionsRulePack(),
		JenkinsRulePack(),
		HelmRulePack(),
		ArgoCDRulePack(),
		TerraformConfigRulePack(),
	}
}
