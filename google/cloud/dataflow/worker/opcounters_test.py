# Copyright 2016 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for worker counters."""

import logging
import unittest

from google.cloud.dataflow.transforms.window import GlobalWindows
from google.cloud.dataflow.worker.opcounters import OperationCounters


class OperationCountersTest(unittest.TestCase):

  def verify_counters(self, opcounts, expected_elements):
    self.assertEqual(expected_elements, opcounts.element_counter.total)
    self.assertEqual(expected_elements, opcounts.element_counter.elements)

  def test_update_int(self):
    opcounts = OperationCounters('some-name')
    self.verify_counters(opcounts, 0)
    opcounts.update(GlobalWindows.WindowedValue(1))
    self.verify_counters(opcounts, 1)

  def test_update_str(self):
    opcounts = OperationCounters('some-name')
    self.verify_counters(opcounts, 0)
    opcounts.update(GlobalWindows.WindowedValue('abcde'))
    self.verify_counters(opcounts, 1)

  def test_update_old_object(self):
    class OldClassThatDoesNotImplementLen:  # pylint: disable=old-style-class

      def __init__(self):
        pass

    opcounts = OperationCounters('some-name')
    self.verify_counters(opcounts, 0)
    obj = OldClassThatDoesNotImplementLen()
    opcounts.update(GlobalWindows.WindowedValue(obj))
    self.verify_counters(opcounts, 1)

  def test_update_new_object(self):
    class ObjectThatDoesNotImplementLen(object):

      def __init__(self):
        pass

    opcounts = OperationCounters('some-name')
    self.verify_counters(opcounts, 0)

    obj = ObjectThatDoesNotImplementLen()
    opcounts.update(GlobalWindows.WindowedValue(obj))
    self.verify_counters(opcounts, 1)

  def test_update_multiple(self):
    opcounts = OperationCounters('some-name')
    self.verify_counters(opcounts, 0)
    opcounts.update(GlobalWindows.WindowedValue('abcde'))
    opcounts.update(GlobalWindows.WindowedValue('defghij'))
    self.verify_counters(opcounts, 2)


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  unittest.main()
