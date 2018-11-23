#!/usr/bin/env python
# -*- Mode: Python -*-
# -*- encoding: utf-8 -*-
# Copyright (c) Vito Caldaralo <vito.caldaralo@gmail.com>

# This file may be distributed and/or modified under the terms of
# the GNU General Public License version 2 as published by
# the Free Software Foundation.
# This file is distributed without any warranty; without even the implied
# warranty of merchantability or fitness for a particular purpose.
# See "LICENSE" in the source distribution for more information.
import os, sys
from utils_py.util import debug, format_bytes
from BaseController import BaseController

DEBUG = 1

# This controller is an implementation of the BBA-0 Controller
# which is an adaptation of BBA-0 Algorithm 1:
# A Buffer-Based Approach to Rate Adaptation:
#Evidence from a Large Video Streaming Service ; Te-Yuan Huang, Ramesh Johari, Nick McKeown, Matthew Trunnel, Mark Watson

class ConventionalController(BaseController):

    def __init__(self):
        super(ConventionalController, self).__init__()
        self.iteration = 0
        self.t_last = -1
        self.filter_old = -1
        #Controller parameters
        self.Q = 30 #seconds
        self.alpha = 0.2 #Ewma filter
        self.eps = 0.15
        self.steady_state = False

    def __repr__(self):
        return '<ConventionalController-%d>' %id(self)

    def calcControlAction(self):    
        T = self.feedback['last_download_time']
        cur = self.feedback['cur_rate']
        tau = self.feedback['fragment_duration']
        x = cur * tau / T
        y = self.__ewma_filter(x) 
        self.setIdleDuration(tau-T)
        debug(DEBUG, "%s calcControlAction: y: %s/s x: %s/s T: %.2f", self, 
            format_bytes(y), format_bytes(x), T)
	# For BBA0
        est_rate = self.__estimateNextRate() # call to estimate the next video rate

        return est_rate

    # for BBA0: Function for estimating the next video rate to be used
    # It is the implementation of the BBA-0 algorithm
    def __estimateNextRate(self):

        #Buffer parameters
	cur = self.feedback['cur_rate'] # the current video rate
	buf_size = self.feedback['max_buffer_time'] # Size of the playback buffer in video seconds
	r = 0.3 * buf_size # Lower reservior contains fixed to 30% of the buffer
	ur = 0.1 * buf_size # Upper reservior is fixed to 10% of the buffer size
        cu = buf_size - (r + ur) # the size of the cushion

	video_rates = self.feedback['rates']
    	r_min = self.feedback['min_rate'] 
    	r_max = self.feedback['max_rate']
	buf_now = self.feedback['queued_time'] # Current buffer occupancy in video seconds
        r_plus = r_min
    	r_minus = r_min
        r_next = r_min

        if cur == r_max:
            r_plus = r_max
        else:
            r_plus = min([i for i in video_rates if i > cur])
        if cur == r_min:
            r_minus = r_min
        else:
            r_minus = max([i for i in video_rates if i < cur])
        if buf_now <= r:
            r_next = r_min
        elif buf_now >= (r + cu):
            r_next = r_max
        elif self.__l_buf(buf_now, r, cu, r_max, r_min) >= r_plus:
            r_nex = max([i for i in video_rates if i < self.__l_buf(buf_now, r, cu, r_max, r_min)])
        elif self.__l_buf(buf_now, r, cu, r_max, r_min) <= r_minus:
            r_next = min([i for i in video_rates if i > self.__l_buf(buf_now, r, cu, r_max, r_min)])
        else:
            r_next = cur

	y = self.__ewma_filter(r_next) 
        return y

    # for BBA0: adjustment function with respect to the current buffer occupancy
    # @Params: buf_now: current buffer occupancy
    #	      resv:size of the lower reservoir
    #         cus: the size of the cushion
    #         r_max: the maximum video rate available
    #         r_min: the minimum video rate available
    # @return: value: estimated next video rate 
    def __l_buf(self, buf_now, resv, cus, r_max, r_min):
        value = (r_max * buf_now - r_max * resv - r_min * buf_now + r_min * resv + r_min * cus)/cus; 
        return value;

    def isBuffering(self):
        return self.feedback['queued_time'] < self.Q

    def quantizeRate(self,rate):

        video_rates = self.feedback['rates']
        cur = self.feedback['cur_rate'] 
        level = self.feedback['level']
        D_up = self.eps*rate
        D_down = 0	
        
        r_up = self.__levelLessThanRate(rate - D_up)
        r_down = self.__levelLessThanRate(rate - D_down)
        new_level = 0
        if level < r_up:
            new_level = r_up
        elif r_up <= level and level <= r_down:
            new_level = level
        else:
            new_level = r_down
        debug(DEBUG, "%s quantizeRate: rate: %s/s cur: %s/s D_up: %s/s D_down: %s/s r_up: %d r_down: %d new_level: %d", self, 
            format_bytes(rate), format_bytes(cur), format_bytes(D_up), format_bytes(D_down), r_up, r_down, new_level)
        debug(DEBUG, "%s quantizeRate: rates: %s", self, video_rates)
        return new_level

    def __ewma_filter(self, x):  #ewma = exponentially weighted moving average
        #First time called
        if self.filter_old < 0:
            self.filter_old = x
            return x
        T = self.feedback['last_download_time']
        y_old = self.filter_old
        y = y_old - T * self.alpha * ( y_old - x )  
        self.filter_old = y
        return y

    def __levelLessThanRate(self, rate):
        vr = self.feedback['rates']
        l = 0
        for i in range(0,len(vr)):
            if rate >= vr[i]:
                l = i
        return l

