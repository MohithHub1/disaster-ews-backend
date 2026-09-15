import pickle
import numpy as np


print("Loading scaler...")

with open("models/scaler.pkl", "rb") as f:
    scaler = pickle.load(f)

print("SCALER LOADED")
print("Expected features:", len(scaler.feature_names_in_))
print("Feature names:")
print(list(scaler.feature_names_in_))


# Create one test row with 30 features
test_data = np.zeros((1, 30), dtype=float)

scaled = scaler.transform(test_data)

print()
print("SCALING SUCCESSFUL")
print("Input shape:", test_data.shape)
print("Output shape:", scaled.shape)
print("First 5 scaled values:", scaled[0][:5])