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

"""Integration tests for the dataflow package."""

from __future__ import absolute_import

import logging
import re
import unittest

from google.cloud.dataflow.pipeline import Pipeline
from google.cloud.dataflow.pvalue import AsDict
from google.cloud.dataflow.pvalue import AsIter as AllOf
from google.cloud.dataflow.pvalue import AsList
from google.cloud.dataflow.pvalue import AsSingleton
from google.cloud.dataflow.pvalue import EmptySideInput
from google.cloud.dataflow.pvalue import SideOutputValue
from google.cloud.dataflow.transforms import Create
from google.cloud.dataflow.transforms import DoFn
from google.cloud.dataflow.transforms import FlatMap
from google.cloud.dataflow.transforms import GroupByKey
from google.cloud.dataflow.transforms import Map
from google.cloud.dataflow.transforms import ParDo
from google.cloud.dataflow.transforms import WindowInto
from google.cloud.dataflow.transforms.util import assert_that
from google.cloud.dataflow.transforms.util import equal_to
from google.cloud.dataflow.transforms.window import IntervalWindow
from google.cloud.dataflow.transforms.window import WindowFn


class DataflowTest(unittest.TestCase):
  """Dataflow integration tests."""

  SAMPLE_DATA = 'aa bb cc aa bb aa \n' * 10
  SAMPLE_RESULT = [('cc', 10), ('bb', 20), ('aa', 30)]

  # TODO(silviuc): Figure out a nice way to specify labels for stages so that
  # internal steps get prepended with surorunding stage names.
  @staticmethod
  def Count(pcoll):  # pylint: disable=invalid-name
    """A Count transform: v, ... => (v, n), ..."""
    return (pcoll
            | Map('AddCount', lambda x: (x, 1))
            | GroupByKey('GroupCounts')
            | Map('AddCounts', lambda (x, ones): (x, sum(ones))))

  def test_word_count(self):
    pipeline = Pipeline('DirectPipelineRunner')
    lines = pipeline | Create('SomeWords', [DataflowTest.SAMPLE_DATA])
    result = (
        (lines | FlatMap('GetWords', lambda x: re.findall(r'\w+', x)))
        .apply('CountWords', DataflowTest.Count))
    assert_that(result, equal_to(DataflowTest.SAMPLE_RESULT))
    pipeline.run()

  def test_map(self):
    pipeline = Pipeline('DirectPipelineRunner')
    lines = pipeline | Create('input', ['a', 'b', 'c'])
    result = (lines
              | Map('upper', str.upper)
              | Map('prefix', lambda x, prefix: prefix + x, 'foo-'))
    assert_that(result, equal_to(['foo-A', 'foo-B', 'foo-C']))
    pipeline.run()

  def test_word_count_using_get(self):
    pipeline = Pipeline('DirectPipelineRunner')
    lines = pipeline | Create('SomeWords', [DataflowTest.SAMPLE_DATA])
    result = (
        (lines | FlatMap('GetWords', lambda x: re.findall(r'\w+', x)))
        .apply('CountWords', DataflowTest.Count))
    assert_that(result, equal_to(DataflowTest.SAMPLE_RESULT))
    pipeline.run()

  def test_par_do_with_side_input_as_arg(self):
    pipeline = Pipeline('DirectPipelineRunner')
    words_list = ['aa', 'bb', 'cc']
    words = pipeline | Create('SomeWords', words_list)
    prefix = pipeline | Create('SomeString', ['xyz'])  # side in
    suffix = 'zyx'
    result = words | FlatMap(
        'DecorateWords',
        lambda x, pfx, sfx: ['%s-%s-%s' % (pfx, x, sfx)],
        AsSingleton(prefix), suffix)
    assert_that(result, equal_to(['xyz-%s-zyx' % x for x in words_list]))
    pipeline.run()

  def test_par_do_with_side_input_as_keyword_arg(self):
    pipeline = Pipeline('DirectPipelineRunner')
    words_list = ['aa', 'bb', 'cc']
    words = pipeline | Create('SomeWords', words_list)
    prefix = 'zyx'
    suffix = pipeline | Create('SomeString', ['xyz'])  # side in
    result = words | FlatMap(
        'DecorateWords',
        lambda x, pfx, sfx: ['%s-%s-%s' % (pfx, x, sfx)],
        prefix, sfx=AsSingleton(suffix))
    assert_that(result, equal_to(['zyx-%s-xyz' % x for x in words_list]))
    pipeline.run()

  def test_par_do_with_do_fn_object(self):
    class SomeDoFn(DoFn):
      """A custom DoFn for a FlatMap transform."""

      def process(self, context, prefix, suffix):
        return ['%s-%s-%s' % (prefix, context.element, suffix)]

    pipeline = Pipeline('DirectPipelineRunner')
    words_list = ['aa', 'bb', 'cc']
    words = pipeline | Create('SomeWords', words_list)
    prefix = 'zyx'
    suffix = pipeline | Create('SomeString', ['xyz'])  # side in
    result = words | ParDo('DecorateWordsDoFn', SomeDoFn(), prefix,
                           suffix=AsSingleton(suffix))
    assert_that(result, equal_to(['zyx-%s-xyz' % x for x in words_list]))
    pipeline.run()

  def test_par_do_with_multiple_outputs_and_using_yield(self):
    class SomeDoFn(DoFn):
      """A custom DoFn using yield."""

      def process(self, context):
        yield context.element
        if context.element % 2 == 0:
          yield SideOutputValue('even', context.element)
        else:
          yield SideOutputValue('odd', context.element)

    pipeline = Pipeline('DirectPipelineRunner')
    nums = pipeline | Create('Some Numbers', [1, 2, 3, 4])
    results = nums | ParDo(
        'ClassifyNumbers', SomeDoFn()).with_outputs('odd', 'even', main='main')
    assert_that(results.main, equal_to([1, 2, 3, 4]))
    assert_that(results.odd, equal_to([1, 3]), label='assert:odd')
    assert_that(results.even, equal_to([2, 4]), label='assert:even')
    pipeline.run()

  def test_par_do_with_multiple_outputs_and_using_return(self):
    def some_fn(v):
      if v % 2 == 0:
        return [v, SideOutputValue('even', v)]
      else:
        return [v, SideOutputValue('odd', v)]

    pipeline = Pipeline('DirectPipelineRunner')
    nums = pipeline | Create('Some Numbers', [1, 2, 3, 4])
    results = nums | FlatMap(
        'ClassifyNumbers', some_fn).with_outputs('odd', 'even', main='main')
    assert_that(results.main, equal_to([1, 2, 3, 4]))
    assert_that(results.odd, equal_to([1, 3]), label='assert:odd')
    assert_that(results.even, equal_to([2, 4]), label='assert:even')
    pipeline.run()

  def test_empty_singleton_side_input(self):
    pipeline = Pipeline('DirectPipelineRunner')
    pcol = pipeline | Create('start', [1, 2])
    side = pipeline | Create('side', [])  # Empty side input.

    def my_fn(k, s):
      v = ('empty' if isinstance(s, EmptySideInput) else 'full')
      return [(k, v)]
    result = pcol | FlatMap('compute', my_fn, AsSingleton(side))
    assert_that(result, equal_to([(1, 'empty'), (2, 'empty')]))
    pipeline.run()

  def test_multi_valued_singleton_side_input(self):
    pipeline = Pipeline('DirectPipelineRunner')
    pcol = pipeline | Create('start', [1, 2])
    side = pipeline | Create('side', [3, 4])  # 2 values in side input.
    pcol | FlatMap('compute', lambda x, s: [x * s], AsSingleton(side))
    with self.assertRaises(ValueError) as e:
      pipeline.run()

  def test_default_value_singleton_side_input(self):
    pipeline = Pipeline('DirectPipelineRunner')
    pcol = pipeline | Create('start', [1, 2])
    side = pipeline | Create('side', [])  # 0 values in side input.
    result = (
        pcol | FlatMap('compute', lambda x, s: [x * s], AsSingleton(side, 10)))
    assert_that(result, equal_to([10, 20]))
    pipeline.run()

  def test_iterable_side_input(self):
    pipeline = Pipeline('DirectPipelineRunner')
    pcol = pipeline | Create('start', [1, 2])
    side = pipeline | Create('side', [3, 4])  # 2 values in side input.
    result = pcol | FlatMap('compute',
                            lambda x, s: [x * y for y in s], AllOf(side))
    assert_that(result, equal_to([3, 4, 6, 8]))
    pipeline.run()

  def test_undeclared_side_outputs(self):
    pipeline = Pipeline('DirectPipelineRunner')
    nums = pipeline | Create('Some Numbers', [1, 2, 3, 4])
    results = nums | FlatMap(
        'ClassifyNumbers',
        lambda x: [x, SideOutputValue('even' if x % 2 == 0 else 'odd', x)]
    ).with_outputs('odd', 'even', main='main')
    # TODO(silviuc): Revisit this test to check for undeclared side outputs.
    # This should work with .with_outputs() without any tags declared and
    # the results[None] should work also.
    assert_that(results.main, equal_to([1, 2, 3, 4]))
    assert_that(results.odd, equal_to([1, 3]), label='assert:odd')
    assert_that(results.even, equal_to([2, 4]), label='assert:even')
    pipeline.run()

  def test_empty_side_outputs(self):
    pipeline = Pipeline('DirectPipelineRunner')
    nums = pipeline | Create('Some Numbers', [1, 3, 5])
    results = nums | FlatMap(
        'ClassifyNumbers',
        lambda x: [x, SideOutputValue('even' if x % 2 == 0 else 'odd', x)]
    ).with_outputs('odd', 'even', main='main')
    assert_that(results.main, equal_to([1, 3, 5]))
    assert_that(results.odd, equal_to([1, 3, 5]), label='assert:odd')
    assert_that(results.even, equal_to([]), label='assert:even')
    pipeline.run()

  def test_as_list_and_as_dict_side_inputs(self):
    a_list = [5, 1, 3, 2, 9]
    some_pairs = [('crouton', 17), ('supreme', None)]
    pipeline = Pipeline('DirectPipelineRunner')
    main_input = pipeline | Create('main input', [1])
    side_list = pipeline | Create('side list', a_list)
    side_pairs = pipeline | Create('side pairs', some_pairs)
    results = main_input | FlatMap(
        'concatenate',
        lambda x, the_list, the_dict: [[x, the_list, the_dict]],
        AsList(side_list), AsDict(side_pairs))

    def  matcher(expected_elem, expected_list, expected_pairs):
      def match(actual):
        [[actual_elem, actual_list, actual_dict]] = actual
        equal_to([expected_elem])([actual_elem])
        equal_to(expected_list)(actual_list)
        equal_to(expected_pairs)(actual_dict.iteritems())
      return match

    assert_that(results, matcher(1, a_list, some_pairs))
    pipeline.run()

  def test_as_list_without_unique_labels(self):
    a_list = [1, 2, 3]
    pipeline = Pipeline('DirectPipelineRunner')
    main_input = pipeline | Create('main input', [1])
    side_list = pipeline | Create('side list', a_list)
    with self.assertRaises(RuntimeError) as e:
      _ = main_input | FlatMap(
          'test',
          lambda x, ls1, ls2: [[x, ls1, ls2]],
          AsList(side_list), AsList(side_list))
    self.assertTrue(
        e.exception.message.startswith(
            'Transform "AsList" does not have a stable unique label.'))

  def test_as_list_with_unique_labels(self):
    a_list = [1, 2, 3]
    pipeline = Pipeline('DirectPipelineRunner')
    main_input = pipeline | Create('main input', [1])
    side_list = pipeline | Create('side list', a_list)
    results = main_input | FlatMap(
        'test',
        lambda x, ls1, ls2: [[x, ls1, ls2]],
        AsList(side_list), AsList(side_list, label='label'))

    def  matcher(expected_elem, expected_list):
      def match(actual):
        [[actual_elem, actual_list1, actual_list2]] = actual
        equal_to([expected_elem])([actual_elem])
        equal_to(expected_list)(actual_list1)
        equal_to(expected_list)(actual_list2)
      return match

  def test_as_dict_with_unique_labels(self):
    some_kvs = [('a', 1), ('b', 2)]
    pipeline = Pipeline('DirectPipelineRunner')
    main_input = pipeline | Create('main input', [1])
    side_kvs = pipeline | Create('side kvs', some_kvs)
    results = main_input | FlatMap(
        'test',
        lambda x, dct1, dct2: [[x, dct1, dct2]],
        AsDict(side_kvs), AsDict(side_kvs, label='label'))

    def  matcher(expected_elem, expected_kvs):
      def match(actual):
        [[actual_elem, actual_dict1, actual_dict2]] = actual
        equal_to([expected_elem])([actual_elem])
        equal_to(expected_kvs)(actual_dict1.iteritems())
        equal_to(expected_kvs)(actual_dict2.iteritems())
      return match

    assert_that(results, matcher(1, some_kvs))
    pipeline.run()

  def test_window_transform(self):
    class TestWindowFn(WindowFn):
      """Windowing function adding two disjoint windows to each element."""

      def assign(self, assign_context):
        _ = assign_context
        return [IntervalWindow(10, 20), IntervalWindow(20, 30)]

      def merge(self, existing_windows):
        return existing_windows

    pipeline = Pipeline('DirectPipelineRunner')
    numbers = pipeline | Create('KVs', [(1, 10), (2, 20), (3, 30)])
    result = (numbers
              | WindowInto('W', windowfn=TestWindowFn())
              | GroupByKey('G'))
    assert_that(
        result, equal_to([(1, [10]), (1, [10]), (2, [20]),
                          (2, [20]), (3, [30]), (3, [30])]))
    pipeline.run()


if __name__ == '__main__':
  logging.getLogger().setLevel(logging.INFO)
  unittest.main()
