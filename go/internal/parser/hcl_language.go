package parser

import (
	"fmt"
	"path/filepath"
	"sort"
	"strings"

	"github.com/hashicorp/hcl/v2"
	"github.com/hashicorp/hcl/v2/hclparse"
	"github.com/hashicorp/hcl/v2/hclsyntax"
	"github.com/zclconf/go-cty/cty"
)

func (e *Engine) parseHCL(
	path string,
	isDependency bool,
	options Options,
) (map[string]any, error) {
	source, err := readSource(path)
	if err != nil {
		return nil, err
	}

	parser := hclparse.NewParser()
	file, diags := parser.ParseHCL(source, path)
	if diags.HasErrors() {
		return nil, fmt.Errorf("parse hcl file %q: %s", path, diags.Error())
	}

	body, ok := file.Body.(*hclsyntax.Body)
	if !ok {
		return nil, fmt.Errorf("parse hcl file %q: unsupported body type %T", path, file.Body)
	}

	payload := hclBasePayload(path, isDependency)
	if strings.EqualFold(filepath.Base(path), "terragrunt.hcl") {
		appendBucket(payload, "terragrunt_configs", parseTerragruntConfig(body, source, path))
	} else {
		parseTerraformBlocks(payload, body, source, path)
	}

	sortNamedBucket(payload, "terraform_resources")
	sortNamedBucket(payload, "terraform_variables")
	sortNamedBucket(payload, "terraform_outputs")
	sortNamedBucket(payload, "terraform_modules")
	sortNamedBucket(payload, "terraform_data_sources")
	sortNamedBucket(payload, "terraform_providers")
	sortNamedBucket(payload, "terraform_locals")
	sortNamedBucket(payload, "terragrunt_configs")
	if options.IndexSource {
		payload["source"] = string(source)
	}
	return payload, nil
}

func hclBasePayload(path string, isDependency bool) map[string]any {
	payload := basePayload(path, "hcl", isDependency)
	payload["terraform_resources"] = []map[string]any{}
	payload["terraform_variables"] = []map[string]any{}
	payload["terraform_outputs"] = []map[string]any{}
	payload["terraform_modules"] = []map[string]any{}
	payload["terraform_data_sources"] = []map[string]any{}
	payload["terraform_providers"] = []map[string]any{}
	payload["terraform_locals"] = []map[string]any{}
	payload["terragrunt_configs"] = []map[string]any{}
	return payload
}

func parseTerraformBlocks(payload map[string]any, body *hclsyntax.Body, source []byte, path string) {
	providerMetadata := collectRequiredProviders(body, source)

	for _, block := range body.Blocks {
		switch block.Type {
		case "resource":
			if len(block.Labels) < 2 {
				continue
			}
			appendBucket(payload, "terraform_resources", map[string]any{
				"name":          block.Labels[0] + "." + block.Labels[1],
				"line_number":   block.TypeRange.Start.Line,
				"resource_type": block.Labels[0],
				"resource_name": block.Labels[1],
				"path":          path,
				"lang":          "hcl",
			})
		case "variable":
			if len(block.Labels) == 0 {
				continue
			}
			appendBucket(payload, "terraform_variables", map[string]any{
				"name":        block.Labels[0],
				"line_number": block.TypeRange.Start.Line,
				"var_type":    attributeValue(block.Body.Attributes["type"], source),
				"default":     attributeValue(block.Body.Attributes["default"], source),
				"description": attributeValue(block.Body.Attributes["description"], source),
				"path":        path,
				"lang":        "hcl",
			})
		case "output":
			if len(block.Labels) == 0 {
				continue
			}
			appendBucket(payload, "terraform_outputs", map[string]any{
				"name":        block.Labels[0],
				"line_number": block.TypeRange.Start.Line,
				"description": attributeValue(block.Body.Attributes["description"], source),
				"value":       attributeValue(block.Body.Attributes["value"], source),
				"path":        path,
				"lang":        "hcl",
			})
		case "module":
			if len(block.Labels) == 0 {
				continue
			}
			row := map[string]any{
				"name":            block.Labels[0],
				"line_number":     block.TypeRange.Start.Line,
				"source":          attributeValue(block.Body.Attributes["source"], source),
				"version":         attributeValue(block.Body.Attributes["version"], source),
				"deployment_name": attributeValue(block.Body.Attributes["name"], source),
				"repo_name":       attributeValue(block.Body.Attributes["repo_name"], source),
				"create_deploy":   attributeValue(block.Body.Attributes["create_deploy"], source),
				"cluster_name":    attributeValue(block.Body.Attributes["cluster_name"], source),
				"zone_id":         attributeValue(block.Body.Attributes["zone_id"], source),
				"path":            path,
				"lang":            "hcl",
			}
			if deployConf := objectAttributeMap(block.Body.Attributes["deploy_conf"], source); len(deployConf) > 0 {
				row["deploy_entry_point"] = deployConf["ENTRY_POINT"]
			}
			appendBucket(payload, "terraform_modules", row)
		case "data":
			if len(block.Labels) < 2 {
				continue
			}
			appendBucket(payload, "terraform_data_sources", map[string]any{
				"name":        block.Labels[0] + "." + block.Labels[1],
				"line_number": block.TypeRange.Start.Line,
				"data_type":   block.Labels[0],
				"data_name":   block.Labels[1],
				"path":        path,
				"lang":        "hcl",
			})
		case "provider":
			if len(block.Labels) == 0 {
				continue
			}
			metadata := providerMetadata[block.Labels[0]]
			appendBucket(payload, "terraform_providers", map[string]any{
				"name":        block.Labels[0],
				"line_number": block.TypeRange.Start.Line,
				"source":      metadata["source"],
				"version":     metadata["version"],
				"alias":       attributeValue(block.Body.Attributes["alias"], source),
				"region":      attributeValue(block.Body.Attributes["region"], source),
				"path":        path,
				"lang":        "hcl",
			})
		case "locals":
			for _, item := range sortedAttributes(block.Body.Attributes) {
				name := item.name
				attribute := item.attribute
				appendBucket(payload, "terraform_locals", map[string]any{
					"name":        name,
					"line_number": attribute.NameRange.Start.Line,
					"value":       expressionText(attribute.Expr, source),
					"path":        path,
					"lang":        "hcl",
				})
			}
		}
	}
}

func collectRequiredProviders(body *hclsyntax.Body, source []byte) map[string]map[string]string {
	result := make(map[string]map[string]string)
	for _, block := range body.Blocks {
		if block.Type != "terraform" {
			continue
		}
		for _, child := range block.Body.Blocks {
			if child.Type != "required_providers" {
				continue
			}
			for _, item := range sortedAttributes(child.Body.Attributes) {
				result[item.name] = objectAttributeMap(item.attribute, source)
			}
		}
	}
	return result
}

func parseTerragruntConfig(body *hclsyntax.Body, source []byte, path string) map[string]any {
	row := map[string]any{
		"name":        strings.TrimSuffix(filepath.Base(path), filepath.Ext(path)),
		"line_number": 1,
		"path":        path,
		"lang":        "hcl",
	}

	includeNames := make([]string, 0)
	localNames := make([]string, 0)
	for _, block := range body.Blocks {
		switch block.Type {
		case "terraform":
			row["terraform_source"] = attributeValue(block.Body.Attributes["source"], source)
		case "include":
			includeNames = append(includeNames, block.Labels...)
		case "locals":
			for name := range block.Body.Attributes {
				localNames = append(localNames, name)
			}
		}
	}
	sort.Strings(includeNames)
	sort.Strings(localNames)
	row["includes"] = strings.Join(includeNames, ",")
	row["locals"] = strings.Join(localNames, ",")
	row["inputs"] = strings.Join(objectAttributeKeys(body.Attributes["inputs"], source), ",")
	return row
}

type namedAttribute struct {
	name      string
	attribute *hclsyntax.Attribute
}

func sortedAttributes(attributes map[string]*hclsyntax.Attribute) []namedAttribute {
	keys := make([]string, 0, len(attributes))
	for key := range attributes {
		keys = append(keys, key)
	}
	sort.Strings(keys)

	rows := make([]namedAttribute, 0, len(keys))
	for _, key := range keys {
		rows = append(rows, namedAttribute{name: key, attribute: attributes[key]})
	}
	return rows
}

func attributeValue(attribute *hclsyntax.Attribute, source []byte) string {
	if attribute == nil {
		return ""
	}
	return expressionText(attribute.Expr, source)
}

func objectAttributeMap(attribute *hclsyntax.Attribute, source []byte) map[string]string {
	if attribute == nil {
		return nil
	}
	objectExpr, ok := attribute.Expr.(*hclsyntax.ObjectConsExpr)
	if !ok {
		return nil
	}
	result := make(map[string]string, len(objectExpr.Items))
	for _, item := range objectExpr.Items {
		name := strings.Trim(expressionText(item.KeyExpr, source), `"`)
		if strings.TrimSpace(name) == "" {
			continue
		}
		result[name] = expressionText(item.ValueExpr, source)
	}
	return result
}

func objectAttributeKeys(attribute *hclsyntax.Attribute, source []byte) []string {
	if attribute == nil {
		return nil
	}
	objectExpr, ok := attribute.Expr.(*hclsyntax.ObjectConsExpr)
	if !ok {
		return nil
	}
	keys := make([]string, 0, len(objectExpr.Items))
	for _, item := range objectExpr.Items {
		key := strings.Trim(expressionText(item.KeyExpr, source), `"`)
		if strings.TrimSpace(key) != "" {
			keys = append(keys, key)
		}
	}
	sort.Strings(keys)
	return keys
}

func expressionText(expr hclsyntax.Expression, source []byte) string {
	if expr == nil {
		return ""
	}
	var text string
	switch typed := expr.(type) {
	case *hclsyntax.LiteralValueExpr:
		text = literalValueText(typed)
	case *hclsyntax.TemplateExpr:
		text = strings.TrimSpace(sourceRange(source, typed.Range()))
	case *hclsyntax.ObjectConsExpr:
		text = strings.TrimSpace(sourceRange(source, typed.Range()))
	case *hclsyntax.ScopeTraversalExpr:
		text = strings.TrimSpace(sourceRange(source, typed.Range()))
	default:
		text = strings.TrimSpace(sourceRange(source, expr.Range()))
	}
	return strings.Trim(text, `"`)
}

func literalValueText(expr *hclsyntax.LiteralValueExpr) string {
	if expr == nil {
		return ""
	}
	if expr.Val.Type() == cty.String {
		return expr.Val.AsString()
	}
	return strings.TrimSpace(expr.Val.GoString())
}

func sourceRange(source []byte, valueRange hcl.Range) string {
	start := valueRange.Start.Byte
	end := valueRange.End.Byte
	if start < 0 {
		start = 0
	}
	if end > len(source) {
		end = len(source)
	}
	if start >= end {
		return ""
	}
	return string(source[start:end])
}
