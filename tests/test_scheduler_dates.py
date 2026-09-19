from test_wallet_release import SOURCE
import unittest
from unittest.mock import patch
from scheduler_api import parse, SchedulerClient, APIError


class SchedulerDateTests(unittest.TestCase):
    def test_same_korean_day_formats(self):
        for date in ['2026-09-19', '2026-09-19T00:00:00+09:00',
                     '2026-09-18T15:00:00Z', '2026-09-19T10:20:30.123+09:00',
                     '2026-09-19T10:20:30', '2026-09-19 10:20:30']:
            with self.subTest(date=date):
                result = parse({'date':date, 'boss_contents':[{'complete_flag':'true'}]}, '2026-09-19')
                self.assertEqual(result['date'], '2026-09-19')
                self.assertTrue(result['bosses'][0]['done'])

    def test_previous_day_not_reported_as_today(self):
        for date in ['2026-09-18', '2026-09-18T14:59:59Z']:
            with self.assertRaisesRegex(APIError, '기준일 2026-09-18'):
                parse({'date':date}, '2026-09-19')

    def test_missing_date_is_distinct(self):
        for date in [None, '', 123]:
            with self.assertRaisesRegex(APIError, '기준 날짜가 없습니다'):
                parse({'date':date}, '2026-09-19')

    def test_invalid_dates_not_sliced_or_assumed(self):
        for date in ['2026-09-19garbage', '2026-02-30', '2026-09-19T25:00:00Z']:
            with self.assertRaisesRegex(APIError, '형식'):
                parse({'date':date}, '2026-09-19')

    @patch('scheduler_api.today', return_value='2026-09-19')
    def test_client_timestamp_response(self, today):
        client = SchedulerClient('test')
        with patch.object(client, '_json', side_effect=[{'ocid':'test'}, {'date':'2026-09-19T00:00:00+09:00'}]):
            self.assertEqual(client.state('test')['date'], '2026-09-19')

    @patch('scheduler_api.today', side_effect=['2026-09-18','2026-09-19'])
    def test_midnight_still_rejected(self, today):
        client = SchedulerClient('test')
        with patch.object(client, '_json', side_effect=[{'ocid':'test'}, {'date':'2026-09-18T23:59:59+09:00'}]):
            with self.assertRaisesRegex(APIError, '날짜가 바뀌었습니다'):
                client.state('test')
