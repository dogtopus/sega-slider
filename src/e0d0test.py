#!/usr/bin/env python3

import unittest
from e0d0 import E0D0Context

class TestE0D0Context(unittest.TestCase):
    def test_decode(self):
        '''Decode (regular)'''
        case = b'\xe0\x00\x01\x02\x03'
        expected = (b'\x00\x01\x02\x03', )
        ctx = E0D0Context()
        actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_decode_escape(self):
        '''Decode (escape)'''
        case = b'\xe0\xd0\xdf\xd0\xcfcode'
        expected = (b'\xe0\xd0code', )
        ctx = E0D0Context()
        actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_decode_multipacket(self):
        '''Multipacket decode'''
        case = b'\xe0first\xe0second'
        expected = (b'first', b'second')
        ctx = E0D0Context()
        actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_decode_multipacket_chained(self):
        '''Multipacket decode (chained)'''
        case1 = b'\xe0first'
        case2 = b'\xe0second'
        expected1 = (b'first',)
        expected2 = (b'second',)
        ctx = E0D0Context()
        actual = ctx.decode(case1)
        self.assertEqual(actual, expected1)
        actual = ctx.decode(case2)
        self.assertEqual(actual, expected2)

    def test_decode_multipacket_chained_incomplete(self):
        '''Multipacket decode (chained and incomplete)'''
        case1 = b'\xe0third\xe0for'
        case2 = b'th'
        expected1 = (b'third', b'for')
        expected2 = (b'th',)
        ctx = E0D0Context()
        actual = ctx.decode(case1)
        self.assertEqual(actual, expected1)
        actual = ctx.decode(case2)
        self.assertEqual(actual, expected2)

    def test_decode_trailing_sync(self):
        '''Trailing sync'''
        case = b'\xe0endless\xe0'
        expected = (b'endless', b'')
        ctx = E0D0Context()
        actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_decode_bad_all_sync(self):
        '''Bad packet (all sync)'''
        case = b'\xe0\xe0\xe0'
        expected = (b'',)
        ctx = E0D0Context()
        actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_decode_bad_sync_after_escape(self):
        '''Bad packet (sync after escape)'''
        case = b'\xe0I am escaping...\xd0\xe0oh'
        expected = (b'I am escaping...', b'oh')
        ctx = E0D0Context()
        with self.assertWarnsRegex(UserWarning, r'^Sync received after escape'):
            actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_decode_bad_escape_after_escape(self):
        '''Bad packet (escape after escape)'''
        case = b'\xe0one\xd0\xd0swo'
        expected = (b'onetwo', )
        ctx = E0D0Context()
        with self.assertWarnsRegex(UserWarning, r'^Escape received after escape'):
            actual = ctx.decode(case)
        self.assertEqual(actual, expected)

    def test_encode(self):
        '''Encode (regular)'''
        case = b'\x00\x01\x02\x03'
        expected = b'\xe0\x00\x01\x02\x03'
        ctx = E0D0Context()
        actual = ctx.finalize(case)
        self.assertEqual(actual, expected)

    def test_encode_escape(self):
        '''Encode (escape)'''
        case = b'\xe0\xd0code'
        expected = b'\xe0\xd0\xdf\xd0\xcfcode'
        ctx = E0D0Context()
        actual = ctx.finalize(case)
        self.assertEqual(actual, expected)

    def test_encode_chaining(self):
        '''Chaining encode'''
        case1 = b'this is '
        case2 = b'one message'
        expected = b'\xe0this is one message'
        ctx = E0D0Context()
        actual = ctx.encode(case1)
        actual += ctx.finalize(case2)
        self.assertEqual(actual, expected)

    def test_encode_multipacket(self):
        '''Multipacket encode'''
        case1 = b'this is'
        case2 = b'two messages'
        expected1 = b'\xe0this is'
        expected2 = b'\xe0two messages'
        ctx = E0D0Context()
        actual = ctx.finalize(case1)
        self.assertEqual(actual, expected1)
        actual = ctx.finalize(case2)
        self.assertEqual(actual, expected2)

if __name__ == '__main__':
    unittest.main()
