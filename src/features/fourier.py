import numpy as np
import pandas as pd
def apply_fourier_transform(df, column='Close', components=[3, 6, 9]):
    data = df[column].values
    n = len(data)
    fft_vals = np.fft.fft(data)
    for comp in components:
        fft_list = np.copy(fft_vals)
        fft_list[comp:-comp] = 0
        df[f'Fourier_{comp}'] = np.fft.ifft(fft_list).real
    return df