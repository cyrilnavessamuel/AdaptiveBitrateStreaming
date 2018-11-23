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

# This controller is an Improvement of the BBA-0 Controller
# which is an adaptation of BBA-1:
# A Buffer-Based Approach to Rate Adaptation:
#Evidence from a Large Video Streaming Service ; Te-Yuan Huang, Ramesh Johari, Nick McKeown, Matthew Trunnel, Mark Watson

class ConventionalController(BaseController):

    def __init__(self):
        super(ConventionalController, self).__init__()
        self.iteration = 0
        self.t_last = -1
        self.filter_old = -1
        #Controller parameters
        self.Q = 40 #seconds
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
	    bw = self.feedback['bwe']

        #Effective Rate: Bandwith - Current Video Rate
	    eff_rate = (bw - cur) 
		# Get the current Fragment size being downloaded
        chunk_size = self.feedback['last_fragment_size']
        #For Dynamic Reservoir bsed on chunk size
        r = chunk_size/eff_rate

	    #Buffer parameters
	    buf_size = self.feedback['max_buffer_time'] # Size of the playback buffer in video seconds
	    ur = 0.1 * buf_size # Upper reservior is fixed to 10% of the buffer size
        cu = buf_size - (r + ur) # the size of the cushion

	    # BBA-1
		#Get the available chunksizes for the give index
        chunkSizes = self.chunkSizefromrates()
        chunk_min = min(chunkSizes)
        chunk_max = max(chunkSizes)

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
            rate_plus = min([i for i in video_rates if i > cur])
        if cur == r_min:
            r_minus = r_min
        else:
            r_minus = max([i for i in video_rates if i < cur])
        if buf_now <= r:
            r_next = r_min
        elif buf_now >= (r + cu):
            r_next = r_max
        elif self.lb_ChunkMap(buf_now, r, cu, chunk_max, chunk_min) >= r_plus:
            r_nex = max([i for i in video_rates if i < self.lb_ChunkMap(buf_now, r, cu, chunk_max, chunk_min)])
        elif self.lb_ChunkMap(buf_now, r, cu, chunk_max, chunk_min) <= r_minus:
            r_next = min([i for i in video_rates if i > self.lb_ChunkMap(buf_now, r, cu, chunk_max, chunk_min)])
        else:
            r_next = cur

	y = self.__ewma_filter(r_next) 

        return y

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

    # For BBA-1: a map function that determines the next rate according to a given size
    def lb_ChunkMap(self, buf_now, resv, cus, chunk_max, chunk_min):
        value = (chunk_max * buf_now - chunk_max * resv - chunk_min * buf_now + chunk_min * resv + chunk_min * cus)/cus
        return value

    # for BBA-1: a function that determines chunk sizes for the current index
    def chunkSizefromrates(self):
        #Derive the playlist from the server, value is added in Tapas Player feedback dictionary
        c = self.feedback['playlists_segmenti']
		#Get the current index of segment needed
        ind = self.feedback['cur_indexi']
		#List containing all the chunk sizes for all the levels 0-5
        tot_seg_byte = []
		#To be return chunk size list for the index
        chunk_size_index = []
		#For each level we get the segments key
        for i in range(len(c)):
            segment = c[i]['segments']
            seg_byte=[]
			#For each segments we get the byterange
            for s in range(len(segment)):
              byte_range= segment[s]['byterange']
			  #We split the byterange to determine the effective chunk size
              byteplit_seg = byte_range.split('-')
			  #Convert the split bytrange to integer and then obtain the difference to get the chunk size
              diffbyte=int(byteplit_seg[1])-int(byteplit_seg[0])
              seg_byte.append(diffbyte)
            tot_seg_byte.append(seg_byte)
			#Get the chunk size for the particular index from all levels
        for k in range(len(tot_seg_byte)):
            chunk_size_index.append(tot_seg_byte[k][ind-1])
        
        return chunk_size_index

