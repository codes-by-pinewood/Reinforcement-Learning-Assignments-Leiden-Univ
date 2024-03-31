# -*- coding: utf-8 -*-
"""dqn_with_diff_epsilons.ipynb

Automatically generated by Colaboratory.

Original file is located at
    https://colab.research.google.com/drive/1oJvh0tTiUSQW_9cY4pGmEymkCaSioV1P
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
        self.size = 2000 #capacity of buffer
        self.batchsize = batchsize

        #给记忆五元组申请空间
        self.s = np.empty(shape = (self.size, self.n_state), dtype=np.float32)
        self.a = np.random.randint(low=0, high=n_action, size=self.size, dtype=np.uint8)
        self.r = np.empty(self.size, dtype=np.float32)
        self.done = np.random.randint(low=0, high=2, size=self.size, dtype=np.uint8)
        self.s_ = np.empty(shape = (self.size, self.n_state), dtype=np.float32)

        self.t = 0
        self.tmax = 0  # initialise tmax

    def add_memo(self,s,a,r,done,s_): #需要实现功能：1.交互后增加记忆 2.sample batch时取出记忆
    #第t步向记忆池里加记忆
        self.s[self.t] = s
        self.a[self.t] = a
        self.r[self.t] = r
        self.done[self.t] = done
        self.s_[self.t] = s_
        self.t = self.t + 1 if self.t + 1 < self.size else 1 #t到2001时，重新从1开始加
        self.tmax = max(self.tmax, self.t +1)



    def sample(self):
    #采样逻辑：Buffer里的经验如果比batchsize多，那就sample;如果比batchsize少，那就有几个取几个

        if self.tmax > self.batchsize:
           k = self.batchsize  # 如果缓冲区样本数大于等于批次大小，使用批次大小
        else:
           k = self.tmax  # 否则，使用缓冲区的实际样本数量

        idxes = random.sample(range(0, self.tmax), k)  # 使用确定的k值抽样

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

        #convert numpy arrays to torch tensors
        batch_s = torch.as_tensor(np.asarray(batch_s),dtype=torch.float32)
        batch_a = torch.as_tensor(np.asarray(batch_a),dtype=torch.int64).unsqueeze(-1) #dimension from (2) to (2,1)
        batch_r = torch.as_tensor(np.asarray(batch_r),dtype=torch.float32).unsqueeze(-1)
        batch_done = torch.as_tensor(np.asarray(batch_done),dtype=torch.float32).unsqueeze(-1)
        batch_s_ = torch.as_tensor(np.asarray(batch_s_),dtype=torch.float32)

        return batch_s, batch_a, batch_r, batch_done, batch_s_

class Qnetwork(nn.Module):
      def __init__(self, n_input, n_output):
          super().__init__() #initialise module

          self.net = nn.Sequential(
              nn.Linear(in_features= n_input, out_features = 128),
              nn.ReLU(),
              nn.Linear(in_features= 128, out_features = n_output))

      def forward(self,x):
           return self.net(x) #forward propagation

      def act(self,obs): #With obs find maximum Q value and corresponding action
          obs_tensor = torch.as_tensor(obs, dtype=torch.float32)
          q_value = self(obs_tensor.unsqueeze(0)) #convert to row vector
          max_q_idx = torch.argmax(input=q_value)
          action = max_q_idx.detach().item() #find action corresponding to max Q index
          return action


class AgentwRB:
   def __init__(self, n_input, n_output,  batchsize, Gamma=0.97, learning_rate = 0.01):
            self.n_input = n_input
            self.n_output = n_output
            self.learning_rate = learning_rate
            self.Gamma = Gamma
            self.batchsize = batchsize
            self.memo = Replaybuffer(self.n_input, self.n_output, self.batchsize)

            #initialise online network and target network
            self.online_net = Qnetwork(self.n_input, self.n_output)
            self.target_net = Qnetwork(self.n_input, self.n_output)

            self.optimizer = torch.optim.Adam(self.online_net.parameters(),lr=self.learning_rate)

##EPSILON START = 0.01

env = gym.make('CartPole-v1')
n_input = env.observation_space.shape[0]
n_output = env.action_space.n

epsilon_decay = 10000
epsilon_start = 0.01 #best value from tuning hyperparameters
epsilon_end = 0.01
n_step = 500
n_episode = 1000
TARGET_UPDATE = 10
Gamma=0.97
learning_rate = 0.01
s = env.reset()
agent = AgentwRB(n_input, n_output, 64)
episode_array = []
rewards_array = []
Reward_list = np.empty(shape=n_episode)
n_episode = 1000

for episode in range(n_episode):
    epi_reward = 0
    for step in range(n_step):
        'epsilon greedy with decay of epsilon'
        epsilon = np.interp(episode * n_step + step, [0, epsilon_decay], [epsilon_start, epsilon_end])

        random_sample = random.random()
        if random_sample <= epsilon:
           a = env.action_space.sample()
        else:
           a = agent.online_net.act(s)

        'Interact with the env'
        s_, r, done, _ = env.step(a) #get next state, reward, done and info
        agent.memo.add_memo(s, a, r, done, s_) #append to replay buffer
        s = s_ #store transition
        epi_reward += r

        if done:
           s = env.reset()
           Reward_list[episode] = epi_reward #store episode reward
           break

        '''Sample minibatches from the transition'''
        batch_s, batch_a, batch_r, batch_done, batch_s_ = agent.memo.sample()

        '''Compute Q_target'''
        target_q_values = agent.target_net(batch_s_)
        target_q = batch_r + agent.Gamma * (1-batch_done) * target_q_values.max(dim=1, keepdim=True)[0]
        '''Compute Q_pred'''
        pred_q_values = agent.online_net(batch_s) #For each state in batch get Q value for each action
        pred_q = torch.gather(input=pred_q_values, dim=1, index=batch_a)
        #According to the action index specified in batch_a, select the corresponding action from the action Q value pred_q_values ​​of each state
        '''Compute Loss, gredient descent'''
        loss = nn.functional.smooth_l1_loss(target_q, pred_q)
        agent.optimizer.zero_grad()
        loss.backward()
        agent.optimizer.step() #apply descent according to gradient

        '''Fix Q-target'''
    if episode % TARGET_UPDATE ==0:
        agent.target_net.load_state_dict(agent.online_net.state_dict())
        reward = np.mean(Reward_list[episode-10:episode])
        print("Episode:{}".format(episode))
        print("Reward:{}".format(reward))
        episode_array.append(episode)
        rewards_array.append(reward)

##EPSILON START = 0.1

s = env.reset()
agent = AgentwRB(n_input, n_output, 64)
episode2_array = []
rewards2_array = []
Reward_list = np.empty(shape=n_episode)
n_episode = 1000
epsilon_start = 0.1

for episode in range(n_episode):
    epi_reward = 0
    for step in range(n_step):
        'epsilon greedy with decay of epsilon'
        epsilon = np.interp(episode * n_step + step, [0, epsilon_decay], [epsilon_start, epsilon_end])

        random_sample = random.random()
        if random_sample <= epsilon:
           a = env.action_space.sample()
        else:
           a = agent.online_net.act(s)


        'Interact with the env'
        s_, r, done, _ = env.step(a) #get next state, reward, done, info
        agent.memo.add_memo(s, a, r, done, s_) #add to replay buffer
        s = s_ #update state
        epi_reward += r

        if done:
           s = env.reset()
           Reward_list[episode] = epi_reward #update episode reward
           break

        '''Sample minibatches from the transition'''
        batch_s, batch_a, batch_r, batch_done, batch_s_ = agent.memo.sample()

        '''Compute Q_target'''
        target_q_values = agent.target_net(batch_s_)
        target_q = batch_r + agent.Gamma * (1-batch_done) * target_q_values.max(dim=1, keepdim=True)[0]
        '''Compute Q_pred'''
        pred_q_values = agent.online_net(batch_s) #For each state get Q value
        pred_q = torch.gather(input=pred_q_values, dim=1, index=batch_a)
        #According to the action index specified in batch_a, select the corresponding action from the action Q value pred_q_values ​​of each state
        '''Compute Loss, gredient descent'''
        loss = nn.functional.smooth_l1_loss(target_q, pred_q)
        agent.optimizer.zero_grad()
        loss.backward()
        agent.optimizer.step() #apply descent according to gradient

        '''Fix Q-target'''
    if episode % TARGET_UPDATE ==0:
        agent.target_net.load_state_dict(agent.online_net.state_dict())
        reward = np.mean(Reward_list[episode-10:episode])
        print("Episode:{}".format(episode))
        print("Reward:{}".format(reward))
        episode2_array.append(episode)
        rewards2_array.append(reward)

##EPSILON START 0.5

s = env.reset()
agent = AgentwRB(n_input, n_output, 64)
episode3_array = []
rewards3_array = []
Reward_list = np.empty(shape=n_episode)
n_episode = 1000
epsilon_start = 0.5

for episode in range(n_episode):
    epi_reward = 0
    for step in range(n_step):
        'epsilon greedy with decay of epsilon'
        epsilon = np.interp(episode * n_step + step, [0, epsilon_decay], [epsilon_start, epsilon_end])

        random_sample = random.random()
        if random_sample <= epsilon:
           a = env.action_space.sample()
        else:
           a = agent.online_net.act(s)

        'Interact with the env'

        s_, r, done, _ = env.step(a) #get next state, reward, done and info
        agent.memo.add_memo(s, a, r, done, s_) #add to replay buffer
        s = s_ #update state
        epi_reward += r


        if done:
           s = env.reset()
           Reward_list[episode] = epi_reward #store episode reward
           break

        '''Sample minibatches from the transition'''
        batch_s, batch_a, batch_r, batch_done, batch_s_ = agent.memo.sample()

        '''Compute Q_target'''
        target_q_values = agent.target_net(batch_s_)
        target_q = batch_r + agent.Gamma * (1-batch_done) * target_q_values.max(dim=1, keepdim=True)[0]
        '''Compute Q_pred'''
        pred_q_values = agent.online_net(batch_s) #for each state in batch, get q vals
        pred_q = torch.gather(input=pred_q_values, dim=1, index=batch_a)
        #According to the action index specified in batch_a, select the corresponding action from the action Q value pred_q_values ​​of each state
        '''Compute Loss, gredient descent'''
        loss = nn.functional.smooth_l1_loss(target_q, pred_q)
        agent.optimizer.zero_grad()
        loss.backward()
        agent.optimizer.step() #apply descent according to gradient

        '''Fix Q-target'''
    if episode % TARGET_UPDATE ==0:
        agent.target_net.load_state_dict(agent.online_net.state_dict())
        reward = np.mean(Reward_list[episode-10:episode])
        print("Episode:{}".format(episode))
        print("Reward:{}".format(reward))
        episode3_array.append(episode)
        rewards3_array.append(reward)

##EPSILON START 0.8

s = env.reset()
agent = AgentwRB(n_input, n_output, 64)
episode4_array = []
rewards4_array = []
Reward_list = np.empty(shape=n_episode)
n_episode = 1000
epsilon_start = 0.8

for episode in range(n_episode):
    epi_reward = 0
    for step in range(n_step):
        'epsilon greedy with decay of epsilon'
        epsilon = np.interp(episode * n_step + step, [0, epsilon_decay], [epsilon_start, epsilon_end])

        random_sample = random.random()
        if random_sample <= epsilon:
           a = env.action_space.sample()
        else:
           a = agent.online_net.act(s)


        'Interact with the env'
        s_, r, done, _ = env.step(a) #get next state, reward, done, info
        agent.memo.add_memo(s, a, r, done, s_) #add to replay buffer
        s = s_ #update state
        epi_reward += r


        if done:
           s = env.reset()
           Reward_list[episode] = epi_reward #store episode reward
           break

        '''Sample minibatches from the transition'''
        batch_s, batch_a, batch_r, batch_done, batch_s_ = agent.memo.sample()

        '''Compute Q_target'''
        target_q_values = agent.target_net(batch_s_)
        target_q = batch_r + agent.Gamma * (1-batch_done) * target_q_values.max(dim=1, keepdim=True)[0]
        '''Compute Q_pred'''
        pred_q_values = agent.online_net(batch_s) #for each state get q vals
        pred_q = torch.gather(input=pred_q_values, dim=1, index=batch_a)
        #According to the action index specified in batch_a, select the corresponding action from the action Q value pred_q_val
        '''Compute Loss, gredient descent'''
        loss = nn.functional.smooth_l1_loss(target_q, pred_q)
        agent.optimizer.zero_grad()
        loss.backward()
        agent.optimizer.step() #apply descent according to gradient

        '''Fix Q-target'''
    if episode % TARGET_UPDATE ==0:
        agent.target_net.load_state_dict(agent.online_net.state_dict())
        reward = np.mean(Reward_list[episode-10:episode])
        print("Episode:{}".format(episode))
        print("Reward:{}".format(reward))
        episode4_array.append(episode)
        rewards4_array.append(reward)

##EPSILON START 1.0

s = env.reset()
agent = AgentwRB(n_input, n_output, 64)
episode5_array = []
rewards5_array = []
Reward_list = np.empty(shape=n_episode)
n_episode = 1000
epsilon_start = 1.0

for episode in range(n_episode):
    epi_reward = 0
    for step in range(n_step):
        'epsilon greedy with decay of epsilon'
        epsilon = np.interp(episode * n_step + step, [0, epsilon_decay], [epsilon_start, epsilon_end])

        random_sample = random.random()
        if random_sample <= epsilon:
           a = env.action_space.sample()
        else:
           a = agent.online_net.act(s)

        'Interact with the env'
        s_, r, done, _ = env.step(a) #get next state, reward, done, info
        agent.memo.add_memo(s, a, r, done, s_) #add to replay buffer
        s = s_ #update state
        epi_reward += r

        if done:
           s = env.reset()
           Reward_list[episode] = epi_reward #store episode reward
           break

        '''Sample minibatches from the transition'''
        batch_s, batch_a, batch_r, batch_done, batch_s_ = agent.memo.sample()

        '''Compute Q_target'''
        target_q_values = agent.target_net(batch_s_)
        target_q = batch_r + agent.Gamma * (1-batch_done) * target_q_values.max(dim=1, keepdim=True)[0]
        '''Compute Q_pred'''
        pred_q_values = agent.online_net(batch_s) #get Q vals
        pred_q = torch.gather(input=pred_q_values, dim=1, index=batch_a)
        #According to the action index specified in batch_a, select the corresponding action from the action Q value pred_q_val
        '''Compute Loss, gredient descent'''
        loss = nn.functional.smooth_l1_loss(target_q, pred_q)
        agent.optimizer.zero_grad()
        loss.backward()
        agent.optimizer.step() #apply descent according to gradient

        '''Fix Q-target'''
    if episode % TARGET_UPDATE ==0:
        agent.target_net.load_state_dict(agent.online_net.state_dict())
        reward = np.mean(Reward_list[episode-10:episode])
        print("Episode:{}".format(episode))
        print("Reward:{}".format(reward))
        episode5_array.append(episode)
        rewards5_array.append(reward)

#Plot the final graph
plt.title("Performance of DQN with varying epsilon values")
plt.plot(episode_array, rewards_array, label = "epsilon = 0.01")
plt.plot(episode2_array, rewards2_array, label = "epsilon = 0.1")
plt.plot(episode3_array, rewards3_array, label = "epsilon = 0.5")
plt.plot(episode4_array, rewards4_array, label = "epsilon = 0.8")
plt.plot(episode4_array, rewards4_array, label = "epsilon = 1.0")

plt.legend()
plt.show()