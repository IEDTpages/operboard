from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

import pandas as pd

import refresh_data


class RefreshDataTests(unittest.TestCase):
    def test_extract_monthly_production_index(self) -> None:
        point = refresh_data._extract_production_point(
            "Индекс промышленного производства в мае 2026 года по сравнению "
            "с маем 2025 года составил 99,3%."
        )
        self.assertEqual(str(point[0]), "2026-05-31")
        self.assertEqual(point[1], 99.3)

    def test_parse_road_freight_wide_workbook(self) -> None:
        output = io.BytesIO()
        pd.DataFrame(
            [
                ["Перевезено грузов автомобильным транспортом, млн т", None, None, None],
                ["Показатель", 2021, 2022, 2023],
                ["Автомобильный транспорт, грузы", 6000.1, 6100.2, 6200.3],
            ]
        ).to_excel(output, index=False, header=False)
        dates, values = refresh_data.parse_rosstat_road_workbook(output.getvalue())
        self.assertEqual(dates, ["2021-12-31", "2022-12-31", "2023-12-31"])
        self.assertEqual(values, [6000.1, 6100.2, 6200.3])

    def test_ati_requires_server_side_secret(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GitHub Secrets"):
                refresh_data.fetch_ati_ftl()

    def test_ati_history_response(self) -> None:
        class Response:
            @staticmethod
            def json() -> dict[str, object]:
                return {
                    "CarType": "all",
                    "Data": [
                        {"Date": "2026-07-15", "Index": 1234.5},
                        {"Date": "2026-07-16", "Index": 1240.0},
                    ],
                }

        with patch.dict(os.environ, {"ATI_API_TOKEN": "test-only"}, clear=True):
            with patch.object(refresh_data, "post_json", return_value=Response()) as post:
                dates, values = refresh_data.fetch_ati_ftl()
        self.assertEqual(dates, ["2026-07-15", "2026-07-16"])
        self.assertEqual(values, [1234.5, 1240])
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "Bearer test-only")


if __name__ == "__main__":
    unittest.main()
