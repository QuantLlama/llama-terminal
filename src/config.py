from src.utils.device_utils import get_best_device
class Config:
    DATA_PATH = 'data/futures_data.csv' 
    SEQ_LENGTH = 60 
    PREDICT_WINDOW = 1 
    BATCH_SIZE = 64
    LEARNING_RATE_G = 0.001
    LEARNING_RATE_D = 0.0004
    LATENT_DIM = 100 
    HIDDEN_DIM_LSTM = 128
    HIDDEN_DIM_CNN = 64
    NUM_LAYERS_LSTM = 2
    NUM_EPOCHS = 200
    CRITIC_ITERATIONS = 5 
    LAMBDA_GP = 10 
    DEVICE = get_best_device()

    USE_FOURIER = True
    USE_SENTIMENT = True
    FOURIER_COMPONENTS = [3, 6, 9]
config = Config()