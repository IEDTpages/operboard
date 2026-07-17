from __future__ import annotations

import io
import os
import unittest
from unittest.mock import patch

import pandas as pd

import refresh_data


class RefreshDataTests(unittest.TestCase):
    def test_cbr_trade_uses_monthly_goods_sheet(self) -> None:
        frame = pd.DataFrame([[None] * 17 for _ in range(9)])
        frame.iat[4, 2] = "Экспорт товаров (ФОБ)"
        frame.iat[4, 8] = "Импорт товаров (ФОБ)"
        frame.iat[4, 14] = "Сальдо торгового баланса"
        frame.iat[5, 2] = "Всего"
        frame.iat[5, 8] = "Всего"
        frame.iat[7, 0] = 2025
        frame.iat[7, 1] = "Янв"
        frame.iat[7, 2] = 40_500
        frame.iat[7, 8] = 25_250
        frame.iat[8, 0] = 2025
        frame.iat[8, 1] = "Фев"
        frame.iat[8, 2] = 41_000
        frame.iat[8, 8] = 26_000

        class Response:
            content = b"workbook"

        with patch.object(refresh_data, "get", return_value=Response()):
            with patch.object(refresh_data.pd, "read_excel", return_value=frame) as read_excel:
                result = refresh_data.fetch_cbr_trade()
        self.assertEqual(read_excel.call_args.kwargs["sheet_name"], "Ежемесячные")
        self.assertEqual(result["exports"], (["2025-01-31", "2025-02-28"], [40.5, 41]))
        self.assertEqual(result["imports"], (["2025-01-31", "2025-02-28"], [25.25, 26]))

    def test_parse_fedstat_filter_metadata(self) -> None:
        html = """
        <html><h1>Тестовый показатель</h1><script>
        const grid = {
          filters: {
            '1': {'title':'Территория','values':{'643':{'title':'Российская Федерация'}}},
            '2': {'title':'Год','values':{'2024':{'title':'2024'},'2025':{'title':'2025'}}}
          },
          left_columns: ['1'],
          top_columns: ['2'],
          groups: [],
          filterObjectIds: []
        };
        grid.init();
        </script></html>
        """
        metadata = refresh_data.parse_fedstat_filter_metadata(html, "57806")
        fields = {item["id"]: item for item in metadata["fields"]}
        self.assertEqual(fields["0"]["values"][0]["id"], "57806")
        self.assertEqual(fields["1"]["object_type"], "lineObjectIds")
        self.assertEqual(fields["2"]["object_type"], "columnObjectIds")
        self.assertEqual(fields["1"]["values"][0]["title"], "Российская Федерация")

    def test_parse_fedstat_sdmx_and_production_modes(self) -> None:
        xml = """<?xml version='1.0' encoding='UTF-8'?>
        <message:GenericData xmlns:message='urn:sdmx:org.sdmx.infomodel.message:2.0'
          xmlns:structure='urn:sdmx:org.sdmx.infomodel.structure:2.0'
          xmlns:generic='urn:sdmx:org.sdmx.infomodel.generic:2.0'>
          <message:CodeLists>
            <structure:CodeList id='activity'><structure:Name>Вид деятельности</structure:Name>
              <structure:Code value='B'><structure:Description>Добыча полезных ископаемых</structure:Description></structure:Code>
            </structure:CodeList>
            <structure:CodeList id='mode'><structure:Name>Вид показателя</structure:Name>
              <structure:Code value='M'><structure:Description>Отчетный месяц к предыдущему месяцу</structure:Description></structure:Code>
            </structure:CodeList>
          </message:CodeLists>
          <message:DataSet><generic:Series><generic:SeriesKey>
            <generic:Value concept='activity' value='B'/><generic:Value concept='mode' value='M'/>
          </generic:SeriesKey><generic:Obs><generic:Time>2025-05</generic:Time>
            <generic:ObsValue value='98,4'/></generic:Obs></generic:Series></message:DataSet>
        </message:GenericData>""".encode("utf-8")
        records = refresh_data.parse_fedstat_sdmx(xml)
        self.assertEqual(records[0]["dimensions"]["Вид деятельности"], "Добыча полезных ископаемых")
        self.assertEqual(records[0]["value"], 98.4)

        modes = {
            "mom": "Отчетный месяц к предыдущему месяцу",
            "yoy": "Отчетный месяц к соответствующему месяцу предыдущего года",
            "ytd_yoy": "Период с начала года к соответствующему периоду предыдущего года",
        }
        lines = {
            "total": "Промышленное производство",
            "mining": "Добыча полезных ископаемых",
            "manufacturing": "Обрабатывающие производства",
        }
        fixture = [
            {
                "time": "2025-05",
                "value": 90 + index,
                "dimensions": {"Вид показателя": mode_label, "Вид деятельности": line_label},
            }
            for index, (mode_label, line_label) in enumerate(
                (mode_label, line_label)
                for mode_label in modes.values()
                for line_label in lines.values()
            )
        ]
        parsed = refresh_data.parse_fedstat_production_records(fixture)
        self.assertEqual(parsed["default_mode"], "mom")
        self.assertEqual(parsed["modes"]["yoy"]["dates"], ["2025-05-31"])
        self.assertEqual(set(parsed["modes"]["mom"]["series"]), set(lines))

    def test_parse_fedstat_road_converts_thousand_tonnes(self) -> None:
        dates, values = refresh_data.parse_fedstat_road_records(
            [
                {
                    "time": "2024",
                    "value": 6_250_000,
                    "dimensions": {"Единица измерения": "тысяча тонн"},
                }
            ]
        )
        self.assertEqual(dates, ["2024-12-31"])
        self.assertEqual(values, [6250])

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
