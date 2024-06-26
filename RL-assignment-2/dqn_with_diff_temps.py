# -*- coding: utf-8 -*-
"""dqn_with_diff_temps.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1vLeojlWhP_JRt-iQ3ALqccJBHudTA0Ek
"""

import gym
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import random
import matplotlib.pyplot as plt
import requests
import numpy as np

class Replaybuffer:
    def __init__(self,n_state,n_action, batchsize):
        self.n_state = n_state
        self.n_action = n_action
        self.size = 2000 #max capacity of replay buffer
        self.batchsize = batchsize

        #initialise batches
        self.s = np.empty(shape = (self.size, self.n_state), dtype=np.float32)
        self.a = np.random.randint(low=0, high=n_action, size=self.size, dtype=np.uint8)
        self.r = np.empty(self.size, dtype=np.float32)
        self.done = np.random.randint(low=0, high=2, size=self.size, dtype=np.uint8)
        self.s_ = np.empty(shape = (self.size, self.n_state), dtype=np.float32)

        self.t = 0
        self.tmax = 0  # initialise tmax

    def add_memo(self,s,a,r,done,s_): #add to replay buffer
        self.s[self.t] = s
        self.a[self.t] = a
        self.r[self.t] = r
        self.done[self.t] = done
        self.s_[self.t] = s_
        self.t = self.t + 1 if self.t + 1 < self.size else 1 #if 2001, reset to 1
        self.tmax = max(self.tmax, self.t +1)



    def sample(self):
        if self.tmax > self.batchsize:
           k = self.batchsize  # if greater than batch size then get batchsize # of samples
        else:
           k = self.tmax  # else get all samples available

        idxes = random.sample(range(0, self.tmax), k)

        batch_s = []
        batch_a = []
        batch_r = []
        batch_done = []
        batch_s_ = []

        for idx in idxes: #extract data
            batch_s.append(self.s[idx])
            batch_a.append(self.a[idx])
            batch_r.append(self.r[idx])
            batch_done.append(self.done[idx])
            batch_s_.append(self.s_[idx])

        #convert numpy arrays to torch tensor
        batch_s = torch.as_tensor(np.asarray(batch_s),dtype=torch.float32)
        batch_a = torch.as_tensor(np.asarray(batch_a),dtype=torch.int64).unsqueeze(-1) #Dim (2,) to (2,1)
        batch_r = torch.as_tensor(np.asarray(batch_r),dtype=torch.float32).unsqueeze(-1)
        batch_done = torch.as_tensor(np.asarray(batch_done),dtype=torch.float32).unsqueeze(-1)
        batch_s_ = torch.as_tensor(np.asarray(batch_s_),dtype=torch.float32)

        return batch_s, batch_a, batch_r, batch_done, batch_s_

class Qnetwork(nn.Module):
      def __init__(self, n_input, n_output):
          super().__init__()

          self.net = nn.Sequential(
              nn.Linear(in_features= n_input, out_features = 128),
              nn.ReLU(),
              nn.Linear(in_features= 128, out_features = n_output))

      def forward(self,x):
           return self.net(x)

      def act(self,obs, temp):
          obs_tensor = torch.as_tensor(obs, dtype=torch.float32)
          q_value = self(obs_tensor.unsqueeze(0))

          softmax_output = F.softmax(q_value/temp, dim = 1)
          action_probs = torch.distributions.Categorical(softmax_output)
          action = action_probs.sample().item()
          return action

#Agent with Replay Buffer and Target Network
class Agent:
   def __init__(self, n_input, n_output,  batchsize, Gamma=0.97, learning_rate = 0.01):
            self.n_input = n_input
            self.n_output = n_output
            self.learning_rate = learning_rate
            self.Gamma = Gamma
            self.batchsize = batchsize
            self.memo = Replaybuffer(self.n_input, self.n_output, self.batchsize)

            self.online_net = Qnetwork(self.n_input, self.n_output)
            self.target_net = Qnetwork(self.n_input, self.n_output)

            self.optimizer = torch.optim.Adam(self.online_net.parameters(),lr=self.learning_rate)

def run(env, agent, n_step, n_episode, temp, target_update):
  s = env.reset()
  episode_array = []
  rewards_array = []
  Reward_list = np.empty(shape=n_episode)

  for episode in range(n_episode):
    epi_reward = 0
    for step in range(n_step):

        a = agent.online_net.act(s, temp)


        s_, r, done, _ = env.step(a) #get next state, reward, done and info
        agent.memo.add_memo(s, a, r, done, s_) #add to replay buffer
        s = s_ #update state
        epi_reward += r

        if done:
           s = env.reset()
           Reward_list[episode] = epi_reward
           break

        '''Sample minibatches from the transition'''
        batch_s, batch_a, batch_r, batch_done, batch_s_ = agent.memo.sample()

        '''Compute Q_target'''
        target_q_values = agent.target_net(batch_s_)
        target_q = batch_r + agent.Gamma * (1-batch_done) * target_q_values.max(dim=1, keepdim=True)[0]
        '''Compute Q_pred'''
        pred_q_values = agent.online_net(batch_s)
        pred_q = torch.gather(input=pred_q_values, dim=1, index=batch_a)

        '''Compute Loss, gredient descent'''
        loss = nn.functional.smooth_l1_loss(target_q, pred_q)
        agent.optimizer.zero_grad()
        loss.backward()
        agent.optimizer.step() #apply descent according to gradient

        '''Fix Q-target'''
    if episode % target_update ==0:
        agent.target_net.load_state_dict(agent.online_net.state_dict())
        reward = np.mean(Reward_list[episode-10:episode])
        print("Episode:{}".format(episode))
        print("Reward:{}".format(reward))
        episode_array.append(episode)
        rewards_array.append(reward)

  return episode_array, rewards_array

def main():
  # Parameters
  env_name = "CartPole-v1"
  env = gym.make(env_name)
  n_input = env.observation_space.shape[0]
  n_output = env.action_space.n

  n_episode = 1000
  n_step = 200
  gamma = 0.97
  target_update = 10

  temp = 0.01

  # Initialize agent for temp = 0.01
  agent = Agent(n_input, n_output, 64)
  e_array, r_array = run(env, agent, n_step, n_episode, temp, target_update)
  env.close()

  temp = 0.1

  # Initialize agent for temp = 0.1
  agent = Agent(n_input, n_output, 64)
  e1_array, r1_array = run(env, agent, n_step, n_episode, temp, target_update)
  env.close()


  temp = 1

  #  Initialize agent for temp = 1
  agent = Agent(n_input, n_output, 64)

  e2_array, r2_array = run(env, agent, n_step, n_episode, temp, target_update)

  env.close()


  temp = 5
  # Initialize agent for temp = 5
  agent = Agent(n_input, n_output, 64)

  e3_array, r3_array = run(env, agent, n_step, n_episode, temp, target_update)

  env.close()


  temp = 10
  # Initialize agent for temp = 10
  agent = Agent(n_input, n_output, 64)
  e4_array, r4_array = run(env, agent, n_step, n_episode, temp, target_update)

  env.close()

  plt.title("Performance of DQN with varying temp values")
  plt.plot(e_array, r_array, label = "temp = 0.01")
  plt.plot(e1_array, r1_array, label = "temp  = 0.1")
  plt.plot(e2_array, r2_array, label = "temp = 1")
  plt.plot(e3_array, r3_array, label = "temp = 5")
  plt.plot(e4_array, r4_array, label = "temp = 10")
  plt.xlabel("Episode")
  plt.ylabel("Rewards")

  plt.legend()
  plt.show()


if __name__ == "__main__":
  main()
