import torch
import torch.nn as nn
import torch.optim as optim
class WGAN_GP:
    def __init__(self, generator, discriminator, config):
        self.generator = generator
        self.discriminator = discriminator
        self.config = config
        self.device = config.DEVICE
        self.g_optimizer = optim.Adam(self.generator.parameters(), lr=config.LEARNING_RATE_G, betas=(0.5, 0.9))
        self.d_optimizer = optim.Adam(self.discriminator.parameters(), lr=config.LEARNING_RATE_D, betas=(0.5, 0.9))
        self.generator.to(self.device)
        self.discriminator.to(self.device)
    def compute_gradient_penalty(self, real_samples, fake_samples):
        alpha = torch.rand((real_samples.size(0), 1, 1)).to(self.device)
        interpolates = (alpha * real_samples + (1 - alpha) * fake_samples).requires_grad_(True)
        d_interpolates = self.discriminator(interpolates)
        fake = torch.ones((real_samples.size(0), 1)).to(self.device)
        gradients = torch.autograd.grad(
            outputs=d_interpolates,
            inputs=interpolates,
            grad_outputs=fake,
            create_graph=True,
            retain_graph=True,
            only_inputs=True,
        )[0]
        gradients = gradients.reshape(gradients.size(0), -1)
        gradient_penalty = ((gradients.norm(2, dim=1) - 1) ** 2).mean()
        return gradient_penalty
    def train_step(self, real_data):
        batch_size = real_data.size(0)
        real_data = real_data.to(self.device)
        for _ in range(self.config.CRITIC_ITERATIONS):
            self.d_optimizer.zero_grad()
            fake_data = self.generator(real_data) 
            real_validity = self.discriminator(real_data)
            fake_validity = self.discriminator(fake_data.detach())
            gradient_penalty = self.compute_gradient_penalty(real_data, fake_data.detach())
            d_loss = -torch.mean(real_validity) + torch.mean(fake_validity) + self.config.LAMBDA_GP * gradient_penalty
            d_loss.backward()
            self.d_optimizer.step()
        self.g_optimizer.zero_grad()
        fake_data = self.generator(real_data)
        fake_validity = self.discriminator(fake_data)
        g_loss = -torch.mean(fake_validity)
        g_loss.backward()
        self.g_optimizer.step()
        return d_loss.item(), g_loss.item()