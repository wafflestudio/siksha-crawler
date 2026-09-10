import datetime
import sys
import unittest
from types import ModuleType
from unittest.mock import patch
from zoneinfo import ZoneInfo


def install_module(name, **attributes):
    module = ModuleType(name)
    for attribute_name, value in attributes.items():
        setattr(module, attribute_name, value)
    sys.modules[name] = module
    return module


install_module("pymysql")
install_module("pytz", timezone=ZoneInfo)
install_module("crawlers")
install_module("crawlers.base_crawler", text_normalizer=lambda value, *_args: value)
install_module("crawlers.snuco_crawler", SnucoRestaurantCrawler=object)
install_module("crawlers.snudorm_crawler", SnudormRestaurantCrawler=object)
install_module("crawlers.vet_crawler", VetRestaurantCrawler=object)
install_module(
    "slack",
    _send_slack_message=lambda *_args: None,
    send_deleted_menus_message=lambda *_args: None,
    send_edited_menus_message=lambda *_args: None,
    send_new_menus_message=lambda *_args: None,
    send_new_restaurants_message=lambda *_args: None,
)

import handler  # noqa: E402


class FakeCursor:
    def __init__(self):
        self.executions = []
        self._result = []

    def execute(self, query, params=None):
        self.executions.append((query, params))
        if "SELECT id, code" in query:
            self._result = [
                {"id": 1, "code": "학생회관식당"},
                {"id": 250, "code": "[축제]테스트식당"},
            ]
        elif "FROM menu AS m" in query:
            self._result = []

    def executemany(self, query, params):
        self.executions.append((query, params))

    def fetchall(self):
        return self._result


class MenusTransactionTest(unittest.TestCase):
    @patch.object(handler, "send_edited_menus_message")
    @patch.object(handler, "send_new_menus_message")
    @patch.object(handler, "send_deleted_menus_message")
    @patch.object(handler, "compare_menus", return_value=([], [], []))
    def test_festival_restaurants_are_excluded_from_sync(
        self,
        compare_menus,
        _send_deleted_menus_message,
        _send_new_menus_message,
        _send_edited_menus_message,
    ):
        cursor = FakeCursor()

        handler.menus_transaction([], cursor)

        menu_query, params = next((query, params) for query, params in cursor.executions if "FROM menu AS m" in query)
        self.assertIn("m.date >= %s", menu_query)
        self.assertIn("r.code NOT LIKE %s", menu_query)
        self.assertIsInstance(params[0], datetime.date)
        self.assertEqual("[축제]%", params[1])
        compare_menus.assert_called_once_with(
            [],
            [],
            [
                {"id": 1, "code": "학생회관식당"},
                {"id": 250, "code": "[축제]테스트식당"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
