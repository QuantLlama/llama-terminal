import torch
import torch.nn as nn
class Discriminator(nn.Module):
    def __init__(self, input_dim, hidden_dim):
        super(Discriminator, self).__init__()
        self.conv1 = nn.Sequential(
            nn.Conv1d(in_channels=input_dim, out_channels=hidden_dim, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2),
            nn.Conv1d(in_channels=hidden_dim, out_channels=hidden_dim*2, kernel_size=3, padding=1),
            nn.LeakyReLU(0.2)
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_dim*2, 1),
        )
    def forward(self, x):
        x = x.permute(0, 2, 1)
        features = self.conv1(x)
        features = torch.mean(features, dim=2)
        validity = self.fc(features)
        return validity