import torch
import torch.nn as nn
class Generator(nn.Module):
    def __init__(self, input_dim, hidden_dim, num_layers, output_dim):
        super(Generator, self).__init__()
        self.hidden_dim = hidden_dim
        self.num_layers = num_layers
        self.lstm = nn.LSTM(input_dim, hidden_dim, num_layers, batch_first=True, dropout=0.2)
        self.linear = nn.Sequential(
            nn.Linear(hidden_dim, output_dim),
            nn.Tanh() 
        )
    def forward(self, x):
        h0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        c0 = torch.zeros(self.num_layers, x.size(0), self.hidden_dim).to(x.device)
        out, _ = self.lstm(x, (h0, c0))
        out = self.linear(out)
        return out
