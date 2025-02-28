import torch
import numpy as np
import torch.nn as nn
import torch.nn.functional as F
from torch.autograd import Variable
import os
class EncoderBlock(nn.Module):
    def __init__(self, input_dim, output_dim):
        super(EncoderBlock, self).__init__()
        self.linear = nn.Linear(input_dim, output_dim)

    def forward(self, input, out=False):
        output = self.linear(input)
        return output


class Encoder(nn.Module):
    def __init__(self, latent_dim, layer, z_size, si_dim):
        super(Encoder, self).__init__()
        self.size = latent_dim
        # layers = []
        # for i in range(layer):
        #     layers.append(EncoderBlock(input_dim=self.size, output_dim=64))
        #     self.size = latent_dim
        # self.inference = nn.Sequential(*layers)


        # print(f'Z_SIZE: {z_size}') # 64
        # print(f'SI_DIM: {si_dim}') # 5120
        # print(f'LATENT_DIM: {latent_dim}') # 64


        self.fc = nn.Sequential(nn.Linear(in_features=(z_size + si_dim), out_features=(latent_dim), bias=False),
                                nn.BatchNorm1d(num_features=latent_dim),
                                nn.Tanh())
        # self.fc = nn.Sequential(nn.Linear(in_features=z_size + si_dim, out_features=latent_dim)
        #                         # nn.BatchNorm1d(num_features=latent_dim),
        #                         # nn.Tanh()
        #                         )

        # in size: 5184 -> 2000 
        # out size: 64  
        # self.fc = nn.Sequential(
        #     nn.Linear(in_features=z_size + si_dim, out_features=latent_dim),
        # )

        temp_size = 2
        self.fc1 = nn.Linear(in_features=z_size + si_dim, out_features=temp_size)
        self.fc2 = nn.Linear(in_features=temp_size, out_features=latent_dim)

        # nn.init.kaiming_uniform_(self.fc.weight, nonlinearity='relu')

        self.l_mu = nn.Linear(in_features= self.size, out_features=z_size)
        self.l_var = nn.Linear(in_features= self.size, out_features=z_size)

        self.l_mu_zgc = nn.Linear(in_features= si_dim, out_features=z_size)
        self.l_var_zgc = nn.Linear(in_features= si_dim, out_features=z_size)

    def forward(self, warm, side_information):
        # warm = self.inference(warm)
        
        mu_zgc = self.l_mu_zgc(side_information)
        logvar_zgc = self.l_var_zgc(side_information)

        print(f'warm: {warm.shape}')
        print(f'side_information: {side_information.shape}')
        
        warm = torch.cat((side_information, warm), 1)
        # print('WARM before go fc: ', warm)
        # print(f'WARM SHAPE: {warm.shape}')

        # psu_weight = np.random.randn(5184, 64)

        # print(f'mat mul test: {warm @ torch.tensor(psu_weight).to(torch.float32).cuda()}')

        # print(f'nan value in WARM: {torch.isnan(warm).sum()}')
        # print(torch.max(warm), torch.min(warm))
        
        # clamp to avoid nan
        # warm = torch.clamp(warm, min=-1e6, max=1e6)

        # normalize 
        # warm = F.normalize(warm, p=2, dim=1)
        # print(f'NORMALIZE WARM: {warm}')    

        warm = self.fc(warm)
        # warm_1 = self.fc1(warm)
        # print(f'WARM after go fc1: {warm_1}')
        # print(f'warm1 shape: {warm_1.shape}')
        # warm = self.fc2(warm_1)

        # print(f'WARM after go fc2: {warm}')
        # print(f'warm shape: {warm.shape}')

        mu = self.l_mu(warm)
        # print(f'WARM before go l_var: {warm}')
        logvar = self.l_var(warm)
        # print(f'LOGVAR in encoder forward: {logvar}')
        return mu, logvar, mu_zgc, logvar_zgc


class DecoderBlock(nn.Module):
    def __init__(self, input_dim, output_dim):
        super(EncoderBlock, self).__init__()


        self.linear = nn.Linear(input_dim, output_dim)
        # self.bn = nn.BatchNorm1d(num_features=dim_out, momentum=0.01, eps=0.001)

    def forward(self, input, out=False):
        output = self.linear(input)
        ten_out = output
        # output = self.bn(output)
        # warm = F.relu(warm, False)
        # output = torch.tanh(output)
        # if out=True return intermediate output for reconstruction error
        if out:
            return output, ten_out
        return output


class Decoder(nn.Module):
    def __init__(self, z_size, latent_dim, layer, si_dim):
        super(Decoder, self).__init__()

        # start from B * z_size
        # concatenate one hot encoded class vector
        self.fc = nn.Sequential(nn.Linear(in_features=(z_size + si_dim), out_features=(latent_dim), bias=False),
                                nn.BatchNorm1d(num_features=latent_dim),
                                nn.Tanh())
        self.size = latent_dim
        layers = []
        for i in range(layer):
            layers.append(EncoderBlock(input_dim=self.size, output_dim=64))
            self.size = latent_dim

        self.geneator = nn.Sequential(*layers)

    def forward(self, z, side_information):
        z_cat = torch.cat((side_information, z), 1)
        rec_warm = self.fc(z_cat)
        rec_warm = self.geneator(rec_warm)
        return rec_warm

class GoRec(nn.Module):
    def __init__(self, env, latent_dim, z_size, si_dim, training=True, encoder_layer=2, decoder_layer=2):
        super(GoRec, self).__init__()
        # latent space size
        self.z_size = z_size
        self.encoder = Encoder(latent_dim=latent_dim , layer=encoder_layer, z_size=self.z_size, si_dim=si_dim)
        # self.de_dim_layer = nn.Linear(in_features=si_dim, out_features=si_dim//2)
        # si_dim = si_dim//2
        self.decoder = Decoder(z_size=self.z_size, latent_dim=latent_dim, layer=decoder_layer, si_dim=si_dim)
        self.env = env
        self.latent = latent_dim
        self.training = training
        self.to(env.device)
        self.dropout = nn.Dropout(p=env.args.dropout)

    def forward(self, warm, side_information, gen_size=10):
        # side_information = self.de_dim_layer(side_information)
        # side_information = torch.tanh(side_information)
        if self.training:
            original = warm


            print(f'warm in forward GoRec: {warm.shape}')

            # encode
            mu, log_variances, mu_zgc, log_variances_zgc = self.encoder(warm, side_information)

            # print(f'LOG_VARIANCES: {log_variances} ')

            # we need true variance not log
            variances = torch.exp(log_variances * 0.5)
            variances_zgc = torch.exp(log_variances_zgc * 0.5)

            # sample from gaussian
            sample_from_normal = Variable(torch.randn(len(warm), self.z_size).to(self.env.device), requires_grad=True)
            sample_from_normal_zgc = Variable(torch.randn(len(warm), self.z_size).to(self.env.device), requires_grad=True)

            # shift and scale using mean and variances
            # print(f'SAMPLE_FROM_NORMAL: {sample_from_normal}')
            # print(f'VARIANCES: {variances}') 
            z = sample_from_normal * variances + mu
            zgc = sample_from_normal_zgc * variances_zgc + mu_zgc

            # decode tensor
            side_information = self.dropout(side_information)
            # print(f'Z IN FORWARD MODEL: {z}')
            rec_warm = self.decoder(z, side_information)
            # print(f'REC_WARM IN FORWARD MODEL: {rec_warm}')

            return rec_warm, mu, log_variances, z, zgc
        else:
            if warm is None:
                # just sample and decode
                z = Variable(torch.randn(gen_size, self.z_size).to(self.env.device), requires_grad=False)
            
            else:
                print(f'warm in test: {warm.shape}')
                print(f'side_information: {side_information.shape}')
                mu, log_variances, _, _ = self.encoder(warm, side_information)
                # torch.save(mu, os.path.join(self.env.DATA_PATH, f'z_u{self.env.args.uni_coeff}_{self.env.args.dataset}.pt'))

                # _, _, mu, log_variances = self.encoder(warm, side_information)
                # we need true variance not log
                variances = torch.exp(log_variances * 0.5)

                # sample from gaussian
                sample_from_normal = Variable(torch.randn(len(warm), self.z_size).to(self.env.device), requires_grad=True)

                # shift and scale using mean and variances
                # z = sample_from_normal * variances + mu
                z =  mu


            # decode tensor
            rec_warm = self.decoder(z, side_information)
            return rec_warm
