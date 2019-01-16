#! /usr/bin/env python
# coding=utf-8
# Copyright (c) 2019 Uber Technologies, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
import math

import numpy as np


def jaccard(sorted_list_1, sorted_list_2):
    max_jaccard_score = 0
    for path1 in sorted_list_1:
        for path2 in sorted_list_2:
            size_set_1 = len(path1)
            size_set_2 = len(path2)

            intersection = 0
            for i in range(min(size_set_1, size_set_2)):
                last_p1 = path1[-(i + 1)]
                last_p2 = path2[-(i + 1)]
                if last_p1 == last_p2:
                    intersection += 1
                else:
                    break

            jaccard_score = intersection / (
                    size_set_1 + size_set_2 - intersection)
            if jaccard_score > max_jaccard_score:
                max_jaccard_score = jaccard_score

    return max_jaccard_score


def softmax(x, temperature=1.0):
    e_x = np.exp((x - np.max(x)) / temperature)
    return e_x / e_x.sum()


def int_type(num_distinct):
    if num_distinct < 128:
        return np.int8
    elif num_distinct < 32768:
        return np.int16
    elif num_distinct < 2147483648:
        return np.int32
    else:
        return np.int64


def convert_size(size_bytes):
    if size_bytes == 0:
        return '0B'
    size_name = ('B', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB')
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return '{} {}'.format(s, size_name[i])