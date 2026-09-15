import tensorflow as tf
import numpy as np


MODEL_PATH = "models/flood_lstm_model.keras"


print("Loading LSTM model...")

model = tf.keras.models.load_model(MODEL_PATH)

print("LSTM LOADED")
print("Input shape:", model.input_shape)
print("Output shape:", model.output_shape)


# ------------------------------------------------------------
# Create a test sequence
# 12 time steps × 30 features
# ------------------------------------------------------------

test_sequence = np.zeros(
    (1, 12, 30),
    dtype=np.float32,
)


prediction = model.predict(
    test_sequence,
    verbose=0,
)


print()
print("LSTM PREDICTION SUCCESSFUL")
print("Input shape:", test_sequence.shape)
print("Raw prediction:", prediction)
print("Flood probability:", float(prediction[0][0]))
