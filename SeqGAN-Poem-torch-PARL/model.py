import torch
import torch.nn as nn
import torch.nn.functional as F


import parl
from parl import layers


class GeneratorAsRLModel(parl.Model):
    def __init__(self, VOCAB_SIZE, g_emb_dim, g_hidden_dim, opt_cuda):
        # in this task, act_dim is VOCAB_SIZE
        # which means to choose words from vocabulary lists

        self.generator = Generator(VOCAB_SIZE, g_emb_dim, g_hidden_dim, opt_cuda)

    def forward(self, obs):  # 可直接用 model = Model(5); model(obs)调用
        out = self.generator.forward(obs)
        return out


class Generator(nn.Module):
    """ Generator """

    def __init__(self, vocab_size, embedding_dim, hidden_dim, use_cuda):
        super(Generator, self).__init__()
        self.hidden_dim = hidden_dim
        self.use_cuda = use_cuda
        self.embed = nn.Embedding(vocab_size, embedding_dim)
        self.lstm = nn.LSTM(embedding_dim, hidden_dim, batch_first=True)
        self.fc = nn.Linear(hidden_dim, vocab_size)
        self.log_softmax = nn.LogSoftmax(dim=1)
        self.init_params()

    def forward(self, x):
        """
        Embeds input and applies LSTM on the input sequence.

        Inputs: x
            - x: (batch_size, seq_len), sequence of tokens generated by generator
        Outputs: out
            - out: (batch_size * seq_len, vocab_size), lstm output prediction
        """
        self.lstm.flatten_parameters()
        h0, c0 = self.init_hidden(x.size(0))
        emb = self.embed(x) # batch_size * seq_len * emb_dim 
        out, _ = self.lstm(emb, (h0, c0)) # out: batch_size * seq_len * hidden_dim
        out = self.log_softmax(self.fc(out.contiguous().view(-1, self.hidden_dim))) # (batch_size*seq_len) * vocab_size
        return out

    def step(self, x, h, c):
        """
        Embeds input and applies LSTM one token at a time (seq_len = 1).

        Inputs: x, h, c
            - x: (batch_size, 1), sequence of tokens generated by generator
            - h: (1, batch_size, hidden_dim), lstm hidden state
            - c: (1, batch_size, hidden_dim), lstm cell state
        Outputs: out, h, c
            - out: (batch_size, vocab_size), lstm output prediction
            - h: (1, batch_size, hidden_dim), lstm hidden state
            - c: (1, batch_size, hidden_dim), lstm cell state 
        """
        self.lstm.flatten_parameters()
        emb = self.embed(x) # batch_size * 1 * emb_dim
        out, (h, c) = self.lstm(emb, (h, c)) # out: batch_size * 1 * hidden_dim
        out = self.log_softmax(self.fc(out.contiguous().view(-1, self.hidden_dim))) # batch_size * vocab_size
        return out, h, c

    def init_hidden(self, batch_size):
        h = torch.zeros(1, batch_size, self.hidden_dim)
        c = torch.zeros(1, batch_size, self.hidden_dim)
        if self.use_cuda:
            h, c = h.cuda(), c.cuda()
        return h, c
    
    def init_params(self):
        for param in self.parameters():
            param.data.uniform_(-0.05, 0.05)

    def sample(self, batch_size, seq_len, x=None):
        """
        Samples the network and returns a batch of samples of length seq_len.

        Outputs: out
            - out: (batch_size * seq_len)
        """
        samples = []
        if x is None:
            h, c = self.init_hidden(batch_size)
            x = torch.zeros(batch_size, 1, dtype=torch.int64)
            if self.use_cuda:
                x = x.cuda()
            for _ in range(seq_len):
                out, h, c = self.step(x, h, c)
                prob = torch.exp(out)
                x = torch.multinomial(prob, 1)
                samples.append(x)
        else:
            h, c = self.init_hidden(x.size(0))
            given_len = x.size(1)
            lis = x.chunk(x.size(1), dim=1)
            for i in range(given_len):
                out, h, c = self.step(lis[i], h, c)
                samples.append(lis[i])
            prob = torch.exp(out)
            x = torch.multinomial(prob, 1)
            for _ in range(given_len, seq_len):
                samples.append(x)
                out, h, c = self.step(x, h, c)
                prob = torch.exp(out)
                x = torch.multinomial(prob, 1)
        out = torch.cat(samples, dim=1) # along the batch_size dimension
        return out
