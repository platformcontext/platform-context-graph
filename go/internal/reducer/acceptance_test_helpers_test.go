package reducer

func acceptedGenerationFixed(generationID string, ok bool) AcceptedGenerationLookup {
	return func(SharedProjectionAcceptanceKey) (string, bool) {
		return generationID, ok
	}
}
