package query

import "strings"

// PythonSemanticSignal identifies a Python-specific semantic that should be
// promoted in query surfaces.
type PythonSemanticSignal string

const (
	// PythonSemanticSignalDecorator marks decorator-driven behavior.
	PythonSemanticSignalDecorator PythonSemanticSignal = "decorator"
	// PythonSemanticSignalAsync marks async function behavior.
	PythonSemanticSignalAsync PythonSemanticSignal = "async"
	// PythonSemanticSignalLambda marks lambda-assignment behavior.
	PythonSemanticSignalLambda PythonSemanticSignal = "lambda"
	// PythonSemanticSignalMetaclass marks class metaclass ownership.
	PythonSemanticSignalMetaclass PythonSemanticSignal = "metaclass"
	// PythonSemanticSignalTypeAnnotation marks type annotation behavior.
	PythonSemanticSignalTypeAnnotation PythonSemanticSignal = "type_annotation"
)

// PythonSemanticProfile summarizes the highest-signal Python metadata a query
// result carries so callers can promote it consistently.
type PythonSemanticProfile struct {
	EntityType     string
	Decorators     []string
	Async          bool
	Lambda         bool
	Metaclass      string
	TypeAnnotation bool
	AnnotationKind string
	Context        string
}

// PythonSemanticProfileFromMetadata builds a promotion profile from a content
// entity type and its metadata payload.
func PythonSemanticProfileFromMetadata(entityType string, metadata map[string]any) PythonSemanticProfile {
	profile := PythonSemanticProfile{EntityType: entityType}
	if len(metadata) == 0 {
		return profile
	}

	profile.Decorators = stringSliceFromAny(metadata["decorators"])
	profile.Async = boolValue(metadata["async"])
	profile.Lambda = metadataString(metadata, "semantic_kind") == "lambda"
	profile.Metaclass = metadataString(metadata, "metaclass")
	profile.AnnotationKind = metadataString(metadata, "annotation_kind")
	profile.Context = metadataString(metadata, "context")
	profile.TypeAnnotation = entityType == "TypeAnnotation" || hasValues(metadata["type_annotations"])
	return profile
}

// HasSignals reports whether the profile contains any Python-specific signals.
func (p PythonSemanticProfile) HasSignals() bool {
	return len(p.Signals()) > 0
}

// PrimarySignal returns the highest-priority semantic signal present.
func (p PythonSemanticProfile) PrimarySignal() PythonSemanticSignal {
	signals := p.Signals()
	if len(signals) == 0 {
		return ""
	}
	return signals[0]
}

// Signals returns the profile signals in promotion priority order.
func (p PythonSemanticProfile) Signals() []PythonSemanticSignal {
	signals := make([]PythonSemanticSignal, 0, 5)
	if len(p.Decorators) > 0 {
		signals = append(signals, PythonSemanticSignalDecorator)
	}
	if p.Async {
		signals = append(signals, PythonSemanticSignalAsync)
	}
	if p.Lambda {
		signals = append(signals, PythonSemanticSignalLambda)
	}
	if p.Metaclass != "" {
		signals = append(signals, PythonSemanticSignalMetaclass)
	}
	if p.TypeAnnotation {
		signals = append(signals, PythonSemanticSignalTypeAnnotation)
	}
	if len(signals) == 0 {
		return nil
	}
	return signals
}

// SurfaceKind returns a small, stable label that the query layer can use when
// promoting Python semantics into story or context surfaces.
func (p PythonSemanticProfile) SurfaceKind() string {
	switch {
	case p.EntityType == "Class" && len(p.Decorators) > 0:
		return "decorated_class"
	case len(p.Decorators) > 0 && p.Async:
		return "decorated_async_function"
	case len(p.Decorators) > 0:
		return "decorated_function"
	case p.Async:
		return "async_function"
	case p.Lambda:
		return "lambda_function"
	case p.EntityType == "Class" && p.Metaclass != "":
		return "metaclass_class"
	case p.TypeAnnotation && p.AnnotationKind == "parameter":
		return "parameter_type_annotation"
	case p.TypeAnnotation && p.AnnotationKind == "return":
		return "return_type_annotation"
	case p.TypeAnnotation:
		return "type_annotation"
	default:
		return "plain"
	}
}

func stringSliceFromAny(value any) []string {
	switch typed := value.(type) {
	case []string:
		return filterEmptyStrings(typed)
	case []any:
		items := make([]string, 0, len(typed))
		for _, item := range typed {
			text, ok := item.(string)
			if !ok {
				continue
			}
			if trimmed := strings.TrimSpace(text); trimmed != "" {
				items = append(items, trimmed)
			}
		}
		return items
	default:
		return nil
	}
}

func filterEmptyStrings(values []string) []string {
	if len(values) == 0 {
		return nil
	}

	items := make([]string, 0, len(values))
	for _, value := range values {
		if trimmed := strings.TrimSpace(value); trimmed != "" {
			items = append(items, trimmed)
		}
	}
	return items
}

func boolValue(value any) bool {
	typed, ok := value.(bool)
	return ok && typed
}

func hasValues(value any) bool {
	switch typed := value.(type) {
	case []string:
		return len(filterEmptyStrings(typed)) > 0
	case []any:
		return len(typed) > 0
	default:
		return false
	}
}
