from __future__ import annotations

import io
import os
import unittest
from datetime import date
from unittest.mock import MagicMock, patch

import pandas as pd
import requests

import refresh_data


class RefreshDataTests(unittest.TestCase):
    def test_space_separated_us_date_is_parsed_without_pandas_warning(self) -> None:
        self.assertEqual(refresh_data.parse_date("07 16 2026"), date(2026, 7, 16))

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

    def test_forecast_economy_levels_build_three_production_modes(self) -> None:
        payload = {
            "indicator": "ipi",
            "count": 24,
            "data": [
                {"date": f"{year}-{month:02d}-01", "value": value}
                for year, base in ((2024, 100), (2025, 110))
                for month, value in (
                    (month, base + month) for month in range(1, 13)
                )
            ],
        }
        total = refresh_data.parse_forecast_economy_level_series(payload, "ipi")
        levels = {
            "total": total,
            "mining": {period: value * 0.9 for period, value in total.items()},
            "manufacturing": {period: value * 1.1 for period, value in total.items()},
        }
        result = refresh_data.build_production_modes_from_levels(
            levels,
            start_date=refresh_data.date(2025, 1, 1),
        )
        self.assertEqual(result["default_mode"], "mom")
        self.assertEqual(result["modes"]["mom"]["dates"][0], "2025-01-31")
        self.assertEqual(result["modes"]["yoy"]["dates"][-1], "2025-12-31")
        self.assertEqual(result["modes"]["ytd_yoy"]["series"]["total"][0], 109.901)
        self.assertEqual(
            set(result["modes"]["mom"]["series"]),
            {"total", "mining", "manufacturing"},
        )

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

    def test_fedstatapir_ids_are_converted_to_filter_metadata(self) -> None:
        metadata = refresh_data._fedstat_ids_to_metadata(
            [
                {
                    "filter_field_id": "0",
                    "filter_field_title": "Показатель",
                    "filter_value_id": "57806",
                    "filter_value_title": "Индекс производства",
                    "filter_field_object_ids": "filterObjectIds",
                },
                {
                    "filter_field_id": "3",
                    "filter_field_title": "Год",
                    "filter_value_id": "2026",
                    "filter_value_title": "2026",
                    "filter_field_object_ids": "columnObjectIds",
                },
            ],
            "57806",
        )
        self.assertEqual(metadata["backend"], "fedstatAPIr")
        self.assertEqual(metadata["title"], "Индекс производства")
        self.assertEqual(metadata["fields"][1]["object_type"], "columnObjectIds")

    def test_fedstatapir_table_is_converted_to_records(self) -> None:
        records = refresh_data._fedstat_table_to_records(
            [
                {
                    "EI": "процент",
                    "ObsValue": "98.4",
                    "Time": "2026-05",
                    "s_POK": "Отчетный месяц к предыдущему месяцу",
                    "s_OKVED2": "Добыча полезных ископаемых",
                    "s_OKVED2_code": "B",
                }
            ]
        )
        self.assertEqual(records[0]["value"], 98.4)
        self.assertEqual(records[0]["unit"], "процент")
        self.assertNotIn("s_OKVED2_code", records[0]["dimensions"])

    def test_fedstatapir_is_default_network_backend(self) -> None:
        metadata = {
            "indicator_id": "31314",
            "title": "Автоперевозки",
            "fields": [
                {
                    "id": "0",
                    "title": "Показатель",
                    "object_type": "filterObjectIds",
                    "values": [{"id": "31314", "title": "Автоперевозки"}],
                }
            ],
        }
        expected = [{"time": "2025", "value": 6250, "dimensions": {}}]
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                refresh_data, "fetch_fedstat_filter_metadata", return_value=metadata
            ):
                with patch.object(
                    refresh_data, "post_fedstat_apir_records", return_value=expected
                ) as post_r:
                    with patch.object(refresh_data, "post_fedstat_sdmx") as post_http:
                        result = refresh_data.fetch_fedstat_records("31314", "road")
        self.assertEqual(result, expected)
        post_r.assert_called_once()
        post_http.assert_not_called()

    def test_road_fedstat_is_not_required_for_other_updates(self) -> None:
        payload = {
            "series": {
                key: {"dates": ["2026-01-31"], "values": [1]}
                for key in ("rubusd", "rubeur", "rubcny", "exports", "imports")
            }
        }
        payload["series"]["production_index"] = {
            "dates": ["2026-01-31"],
            "values": [100.1],
        }
        payload["series"]["road_freight"] = {"dates": [], "values": []}
        with patch.dict(os.environ, {}, clear=True):
            refresh_data.validate_required_currency_series(payload)

    def test_fedstat_can_be_made_strict(self) -> None:
        payload = {
            "series": {
                key: {"dates": ["2026-01-31"], "values": [1]}
                for key in ("rubusd", "rubeur", "rubcny", "exports", "imports")
            }
        }
        payload["series"]["production_index"] = {"dates": [], "values": []}
        payload["series"]["road_freight"] = {"dates": [], "values": []}
        with patch.dict(os.environ, {"FEDSTAT_REQUIRED": "1"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "production_index"):
                refresh_data.validate_required_currency_series(payload)

    def test_fedstat_error_preserves_last_good_marker(self) -> None:
        status = refresh_data.status_source_error(
            {"updated_at": "2026-07-01T00:00:00+00:00"},
            {"dates": ["2026-05-31"], "values": [100.1]},
            "403 Forbidden",
        )
        self.assertEqual(status["state"], "stale")
        self.assertEqual(status["merged_latest"], "2026-05-31")
        self.assertIn("сохранены последние", status["message"])

    def test_extract_monthly_production_index(self) -> None:
        point = refresh_data._extract_production_point(
            "Индекс промышленного производства в мае 2026 года по сравнению "
            "с маем 2025 года составил 99,3%."
        )
        self.assertEqual(str(point[0]), "2026-05-31")
        self.assertEqual(point[1], 99.3)

    def test_parse_rosstat_production_workbook(self) -> None:
        frame = pd.DataFrame([[None] * 6 for _ in range(13)])
        frame.iat[0, 0] = "Индекс производства (процент)"
        frame.iat[2, 3] = 2025
        frame.iloc[3, 3:6] = ["январь", "февраль", "март"]
        activities = {
            "total": "Промышленное производство — всего",
            "mining": "Добыча полезных ископаемых",
            "manufacturing": "Обрабатывающие производства",
        }
        modes = {
            "mom": "Отчетный месяц к предыдущему месяцу",
            "yoy": "Отчетный месяц к соответствующему месяцу предыдущего года",
            "ytd_yoy": "Период с начала года к соответствующему периоду предыдущего года",
        }
        row_index = 4
        for line_index, activity in enumerate(activities.values()):
            for mode_index, mode in enumerate(modes.values()):
                frame.iat[row_index, 0] = "Российская Федерация"
                frame.iat[row_index, 1] = activity
                frame.iat[row_index, 2] = mode
                frame.iloc[row_index, 3:6] = [
                    95 + line_index + mode_index,
                    96 + line_index + mode_index,
                    97 + line_index + mode_index,
                ]
                row_index += 1
        output = io.BytesIO()
        frame.to_excel(output, index=False, header=False)
        parsed = refresh_data.parse_rosstat_production_workbook(output.getvalue())
        self.assertEqual(parsed["modes"]["mom"]["dates"], [
            "2025-01-31", "2025-02-28", "2025-03-31"
        ])
        self.assertEqual(parsed["modes"]["yoy"]["series"]["mining"], [97, 98, 99])

    def test_parse_rosstat_production_months_in_rows(self) -> None:
        output = io.BytesIO()
        activities = [
            "Промышленное производство",
            "Добыча полезных ископаемых",
            "Обрабатывающие производства",
        ]
        modes = {
            "к предыдущему месяцу": 0,
            "к соответствующему месяцу предыдущего года": 2,
            "период с начала года к соответствующему периоду": 4,
        }
        with pd.ExcelWriter(output, engine="openpyxl") as writer:
            for sheet_name, offset in modes.items():
                pd.DataFrame(
                    [
                        [None, *activities],
                        [None, 2026, 2026, 2026],
                        ["январь", 100 + offset, 101 + offset, 102 + offset],
                        ["февраль", 103 + offset, 104 + offset, 105 + offset],
                        ["март", 106 + offset, 107 + offset, 108 + offset],
                    ]
                ).to_excel(writer, sheet_name=sheet_name[:31], index=False, header=False)
        parsed = refresh_data.parse_rosstat_production_workbook(output.getvalue())
        self.assertEqual(
            parsed["modes"]["mom"]["dates"],
            ["2026-01-31", "2026-02-28", "2026-03-31"],
        )
        self.assertEqual(
            parsed["modes"]["ytd_yoy"]["series"]["manufacturing"],
            [106, 109, 112],
        )

    def test_parse_road_freight_wide_workbook(self) -> None:
        output = io.BytesIO()
        pd.DataFrame(
            [
                ["Перевозки грузов по видам транспорта, млн т", None, None, None, None],
                [None, 2025, None, None, None],
                [None, "январь", "февраль", "март", "апрель"],
                ["Автомобильный транспорт", 500.1, 510.2, 520.3, 530.4],
            ]
        ).to_excel(output, index=False, header=False)
        dates, values = refresh_data.parse_rosstat_road_workbook(output.getvalue())
        self.assertEqual(
            dates,
            ["2025-01-31", "2025-02-28", "2025-03-31", "2025-04-30"],
        )
        self.assertEqual(values, [500.1, 510.2, 520.3, 530.4])

    def test_parse_road_freight_single_month_release(self) -> None:
        output = io.BytesIO()
        pd.DataFrame(
            [
                [
                    "Перевезено грузов автомобильным транспортом организаций всех видов "
                    "экономической деятельности, тыс. тонн",
                    None,
                    None,
                ],
                [None, "май 2026", "январь–май 2026"],
                ["Перевезено грузов", 560_500, 2_564_200],
                ["Темп роста, %", 101.2, 99.8],
            ]
        ).to_excel(output, index=False, header=False)
        dates, values = refresh_data.parse_rosstat_road_workbook(output.getvalue())
        self.assertEqual(dates, ["2026-05-31"])
        self.assertEqual(values, [560.5])

    def test_parse_road_freight_months_in_rows(self) -> None:
        output = io.BytesIO()
        pd.DataFrame(
            [
                ["Перевезено грузов автомобильным транспортом, млн тонн", None, None],
                [None, 2025, 2026],
                ["январь", 459.1, 470.2],
                ["февраль", 477.3, 482.4],
                ["март", 529.8, 535.6],
            ]
        ).to_excel(output, index=False, header=False)
        dates, values = refresh_data.parse_rosstat_road_workbook(output.getvalue())
        self.assertEqual(
            dates,
            [
                "2025-01-31", "2025-02-28", "2025-03-31",
                "2026-01-31", "2026-02-28", "2026-03-31",
            ],
        )
        self.assertEqual(values, [459.1, 477.3, 529.8, 470.2, 482.4, 535.6])

    def test_parse_road_cumulative_release_and_derive_month(self) -> None:
        def release(label: str, value: float) -> bytes:
            output = io.BytesIO()
            pd.DataFrame(
                [
                    ["Перевезено грузов автомобильным транспортом (с 2000 г.)", None, None],
                    [label, None, None],
                    ["Год", "Перевезено грузов, млн тонн", "в % к предыдущему периоду"],
                    [2026, value, 101.2],
                ]
            ).to_excel(output, index=False, header=False)
            return output.getvalue()

        may = release("январь–май 2026", 2600.0)
        april = release("январь–апрель 2026", 2050.0)
        self.assertEqual(
            refresh_data._road_release_value(may, date(2026, 5, 31)),
            ("cumulative", 2600),
        )

        urls = [
            "https://rosstat.gov.ru/storage/mediabank/PerevGruz_05-2026.xlsx",
            "https://rosstat.gov.ru/storage/mediabank/PerevGruz_04-2026.xlsx",
        ]
        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                refresh_data,
                "_rosstat_page_candidates",
                side_effect=RuntimeError("temporary page outage"),
            ):
                with patch.object(
                    refresh_data,
                    "rosstat_monthly_workbook_candidates",
                    return_value=urls,
                ):
                    with patch.object(
                        refresh_data,
                        "_download_official_workbook",
                        side_effect=lambda url, attempts=1: may if "05-2026" in url else april,
                    ):
                        dates, values = refresh_data.fetch_rosstat_road_freight()
        self.assertEqual(dates, ["2026-05-31"])
        self.assertEqual(values, [550])

    def test_downloaded_road_workbook_error_is_not_hidden_by_later_404(self) -> None:
        output = io.BytesIO()
        pd.DataFrame([["не та таблица"], [123]]).to_excel(
            output, index=False, header=False
        )
        urls = [
            "https://rosstat.gov.ru/storage/mediabank/PerevGruz_05-2026.xlsx",
            "https://rosstat.gov.ru/storage/mediabank/PerevGruz_04-2026.xlsx",
        ]
        downloads: list[str] = []

        def download(url: str, *, attempts: int = 1) -> bytes:
            downloads.append(url)
            if "05-2026" in url:
                return output.getvalue()
            raise RuntimeError("404 Not Found")

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(refresh_data, "_rosstat_page_candidates", return_value=[]):
                with patch.object(
                    refresh_data,
                    "rosstat_monthly_workbook_candidates",
                    return_value=urls,
                ):
                    with patch.object(
                        refresh_data, "_download_official_workbook", side_effect=download
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError, "PerevGruz_05-2026.xlsx скачан, но не распознан"
                        ):
                            refresh_data.fetch_rosstat_road_freight()
        self.assertEqual(downloads, [urls[0]])

    def test_rosstat_discovery_prefers_current_production_base(self) -> None:
        html = f"""
        <section>Данные по ОКВЭД2 (базисный 2018 год)
          <a href='/storage/mediabank/ind-baza_2018.xlsx'>XLSX</a>
          <span>{refresh_data.ROSSTAT_PRODUCTION_TITLE}</span>
        </section>
        <section>Данные по ОКВЭД2 (базисный 2023 год)
          <a href='/storage/mediabank/ind-baza_2023.xlsx'>XLSX</a>
          <span>{refresh_data.ROSSTAT_PRODUCTION_TITLE}</span>
        </section>
        """
        urls = refresh_data.discover_rosstat_xlsx_urls(
            html,
            refresh_data.ROSSTAT_INDUSTRIAL_URL,
            refresh_data.ROSSTAT_PRODUCTION_TITLE,
            preferred_context="базисный 2023 год",
        )
        self.assertTrue(urls[0].endswith("ind-baza_2023.xlsx"))

    def test_rosstat_discovery_recognises_current_filename_patterns(self) -> None:
        html = """
        <section>
          <a href='/storage/mediabank/PerevGruz_04-2026.xlsx'>XLSX</a>
          <a href='/storage/mediabank/PerevGruz_05-2026.xlsx'>XLSX</a>
        </section>
        """
        urls = refresh_data.discover_rosstat_xlsx_urls(
            html,
            refresh_data.ROSSTAT_TRANSPORT_URL,
            refresh_data.ROSSTAT_ROAD_TITLE,
        )
        self.assertTrue(urls[0].endswith("PerevGruz_05-2026.xlsx"))

    def test_rosstat_monthly_candidates_include_confirmed_current_urls(self) -> None:
        production = refresh_data.rosstat_monthly_workbook_candidates(
            refresh_data.ROSSTAT_PRODUCTION_FILENAME_PREFIX,
            confirmed_url=refresh_data.ROSSTAT_PRODUCTION_XLSX_CONFIRMED,
            as_of=date(2026, 7, 21),
            lookback_months=3,
        )
        road = refresh_data.rosstat_monthly_workbook_candidates(
            refresh_data.ROSSTAT_ROAD_FILENAME_PREFIX,
            confirmed_url=refresh_data.ROSSTAT_ROAD_XLSX_CONFIRMED,
            as_of=date(2026, 7, 21),
            lookback_months=3,
        )
        self.assertTrue(production[0].endswith("ind_baza_2023_06-2026.xlsx"))
        self.assertIn(refresh_data.ROSSTAT_PRODUCTION_XLSX_CONFIRMED, production)
        self.assertTrue(road[0].endswith("PerevGruz_06-2026.xlsx"))
        self.assertIn(refresh_data.ROSSTAT_ROAD_XLSX_CONFIRMED, road)

    def test_current_road_url_is_used_when_catalogue_page_is_unavailable(self) -> None:
        expected = (["2026-05-31"], [560.5])

        def download(url: str, *, attempts: int = 2) -> bytes:
            if url == refresh_data.ROSSTAT_ROAD_XLSX_CONFIRMED:
                return b"workbook"
            raise RuntimeError("404 Not Found")

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(
                refresh_data,
                "_rosstat_page_candidates",
                side_effect=RuntimeError("temporary page outage"),
            ):
                with patch.object(
                    refresh_data,
                    "_download_official_workbook",
                    side_effect=download,
                ):
                    with patch.object(
                        refresh_data,
                        "parse_rosstat_road_workbook",
                        return_value=expected,
                    ):
                        result = refresh_data.fetch_rosstat_road_freight()
        self.assertEqual(result, expected)

    def test_downloaded_production_workbook_error_is_not_hidden_by_later_404(self) -> None:
        output = io.BytesIO()
        pd.DataFrame([["не та таблица"], [99.9]]).to_excel(
            output, index=False, header=False
        )
        urls = [
            "https://rosstat.gov.ru/storage/mediabank/ind_baza_2023_05-2026.xlsx",
            "https://rosstat.gov.ru/storage/mediabank/ind_baza_2023_04-2026.xlsx",
        ]
        downloads: list[str] = []

        def download(url: str, *, attempts: int = 1) -> bytes:
            downloads.append(url)
            if "05-2026" in url:
                return output.getvalue()
            raise RuntimeError("404 Not Found")

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(refresh_data, "_rosstat_page_candidates", return_value=[]):
                with patch.object(
                    refresh_data,
                    "rosstat_monthly_workbook_candidates",
                    return_value=urls,
                ):
                    with patch.object(
                        refresh_data, "_download_official_workbook", side_effect=download
                    ):
                        with self.assertRaisesRegex(
                            RuntimeError,
                            "ind_baza_2023_05-2026.xlsx скачан, но не распознан",
                        ):
                            refresh_data.fetch_rosstat_production_history()
        self.assertEqual(downloads, [urls[0]])

    def test_rosstat_tls_certificate_failure_uses_restricted_fallback(self) -> None:
        class Response:
            status_code = 200
            headers: dict[str, str] = {}

            @staticmethod
            def raise_for_status() -> None:
                return None

        fake_session = MagicMock()
        fake_session.get.side_effect = [
            requests.exceptions.SSLError("[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"),
            Response(),
        ]
        with patch.object(refresh_data, "SESSION", fake_session):
            with patch.object(refresh_data, "_ROSSTAT_TLS_FALLBACK_ACTIVE", False):
                with patch.dict(os.environ, {"ROSSTAT_TLS_FALLBACK": "1"}, clear=False):
                    response = refresh_data.get(
                        "https://rosstat.gov.ru/storage/mediabank/test.xlsx",
                        attempts=1,
                    )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_session.get.call_count, 2)
        self.assertIs(fake_session.get.call_args_list[1].kwargs["verify"], False)
        self.assertIs(fake_session.get.call_args_list[1].kwargs["allow_redirects"], False)

    def test_tls_fallback_is_not_used_for_other_hosts(self) -> None:
        fake_session = MagicMock()
        fake_session.get.side_effect = requests.exceptions.SSLError(
            "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"
        )
        with patch.object(refresh_data, "SESSION", fake_session):
            with patch.object(refresh_data, "_ROSSTAT_TLS_FALLBACK_ACTIVE", False):
                with self.assertRaises(requests.exceptions.SSLError):
                    refresh_data.get("https://example.com/data.xlsx", attempts=1)
        self.assertEqual(fake_session.get.call_count, 1)

    def test_rosstat_tls_fallback_rejects_external_redirect(self) -> None:
        class RedirectResponse:
            status_code = 302
            headers = {"Location": "https://example.com/file.xlsx"}

            @staticmethod
            def close() -> None:
                return None

        fake_session = MagicMock()
        fake_session.get.return_value = RedirectResponse()
        with patch.object(refresh_data, "SESSION", fake_session):
            with self.assertRaisesRegex(requests.exceptions.SSLError, "за пределы"):
                refresh_data._rosstat_get_with_restricted_tls_fallback(
                    "https://rosstat.gov.ru/storage/mediabank/test.xlsx"
                )
        self.assertEqual(fake_session.get.call_count, 1)

    def test_road_override_survives_unavailable_rosstat_page(self) -> None:
        expected = (["2026-05-31"], [555.5])
        with patch.dict(
            os.environ,
            {"ROSSTAT_ROAD_XLSX_URL": "https://rosstat.gov.ru/storage/mediabank/road.xlsx"},
            clear=True,
        ):
            with patch.object(
                refresh_data,
                "_rosstat_page_candidates",
                side_effect=RuntimeError("temporary page outage"),
            ):
                with patch.object(
                    refresh_data,
                    "_download_official_workbook",
                    return_value=b"workbook",
                ):
                    with patch.object(
                        refresh_data,
                        "parse_rosstat_road_workbook",
                        return_value=expected,
                    ):
                        result = refresh_data.fetch_rosstat_road_freight()
        self.assertEqual(result, expected)

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
